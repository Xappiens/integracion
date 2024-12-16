import os
import json
import pandas as pd
import frappe
from frappe import _
from frappe.utils import get_site_path
from frappe.utils.csvutils import read_csv_content
from erpnext.accounts.doctype.bank_statement_import.bank_statement_import import BankStatementImport, start_import
from frappe.utils.file_manager import save_file
from frappe.utils.background_jobs import enqueue



# Sobrescribir la clase BankStatementImport
class CustomBankStatementImport(BankStatementImport):
    log_steps = []
    def validate(self):
        super().validate()
        # Validación adicional: asegurarnos de que la cuenta bancaria tiene un banco asociado
        bank_account = frappe.get_doc("Bank Account", self.bank_account)
        if not bank_account.bank:
            frappe.throw(_("La cuenta bancaria seleccionada no tiene un banco asociado."))

    def start_import(self):
        self.log_steps.append("Iniciando importación personalizada")
        frappe.log_error(message=self.log_steps, title="Log de importación personalizada")

        # Validar que el archivo transformado ya fue procesado
        if not self.import_file:
            frappe.throw(_("Debe seleccionar un archivo para importar."))

        # Sobrescribir el archivo importado con el transformado
        bank_account = frappe.get_doc("Bank Account", self.bank_account)
        bank = frappe.get_doc("Bank", bank_account.bank)
        processed_file_path = self.transform_file(self.import_file, bank, bank_account.name)
        if not os.path.exists(frappe.utils.get_site_path(processed_file_path.strip("/"))):
            frappe.throw(_("El archivo procesado no existe en la ubicación especificada: {0}").format(processed_file_path))

        self.log_steps.append(f"Archivo procesado a utilizar: {processed_file_path}")
        frappe.log_error(message=self.log_steps, title="Log de importación personalizada")

        # Obtener previsualización y verificar columnas necesarias
        preview = frappe.get_doc("Bank Statement Import", self.name).get_preview_from_template(
            processed_file_path, self.google_sheets_url
        )

        from frappe.utils.background_jobs import is_job_enqueued
        from frappe.utils.scheduler import is_scheduler_inactive
        frappe.log_error(message=preview, title="Log de importación PREVIEW")
        # Verificar si el scheduler está activo
        if is_scheduler_inactive() and not frappe.flags.in_test:
            frappe.throw(_("Scheduler is inactive. Cannot import data."), title=_("Scheduler Inactive"))

        # Definir un ID de trabajo único para evitar duplicados
        job_id = f"bank_statement_import::{self.name}"
        if not is_job_enqueued(job_id):
            enqueue(
                start_import,
                queue="default",
                timeout=6000,
                event="data_import",
                job_id=job_id,
                data_import=self.name,
                bank_account=self.bank_account,
                import_file_path=processed_file_path,  # Aseguramos que se utilice el archivo correcto
                google_sheets_url=self.google_sheets_url,
                bank=self.bank,
                template_options=self.template_options,
                now=frappe.conf.developer_mode or frappe.flags.in_test,
            )
            self.log_steps.append(f"Encolando trabajo para importar el archivo procesado: {processed_file_path}")
            frappe.log_error(message=self.log_steps, title="Log de importación personalizada")
            return True

        # Si ya está encolado, no se hace nada
        self.log_steps.append("El trabajo de importación ya está encolado.")
        frappe.log_error(message=self.log_steps, title="Log de importación personalizada")
        return False


    def transform_file(self, file_path, bank, bank_account_name):
        try:
            self.log_steps.append(f"Transformando archivo: {file_path}")

            # Verificar existencia del archivo original
            full_file_path = frappe.utils.get_site_path(file_path.strip("/"))
            if not os.path.exists(full_file_path):
                self.log_steps.append(f"Archivo no encontrado: {full_file_path}")
                frappe.log_error(message=self.log_steps, title="Log de importación")
                frappe.throw(_("El archivo no existe en la ruta especificada: {0}").format(full_file_path))

            self.log_steps.append(f"Archivo encontrado: {full_file_path}")
            file_extension = os.path.splitext(full_file_path)[1].lower()

            # Leer el archivo original
            if file_extension == ".csv":
                file_content = frappe.get_file(file_path).get_content()
                rows = read_csv_content(file_content)
                df = pd.DataFrame(rows[1:], columns=rows[0])
            elif file_extension in [".xlsx", ".xls"]:
                with open(full_file_path, "rb") as file:
                    df = pd.read_excel(file, engine="openpyxl" if file_extension == ".xlsx" else "xlrd")
            else:
                frappe.throw(_("Formato de archivo no soportado: {0}").format(file_extension))

            bank_name = bank.bank_name.lower()
            self.log_steps.append(f"Banco seleccionado: {bank_name}")

            # Procesar según el banco
            if "caixa" in bank_name:
                transformed_data = self.process_caixa(df, bank_account_name)
            elif "santander" in bank_name:
                transformed_data = self.process_santander(df, bank_account_name)
            elif "ibercaja" in bank_name:
                transformed_data = self.process_ibercaja(df, bank_account_name)
            else:
                frappe.throw(_("El banco seleccionado no tiene lógica de transformación implementada."))

            # Renombrar columnas para el importador
# Convertir las columnas a minúsculas antes de renombrarlas
            transformed_data.columns = transformed_data.columns.str.lower()

            # Renombrar las columnas
            transformed_data.rename(columns={
                "fecha valor": "date",
                "referencia": "reference_number",
                "descripción": "description",
                "deposit": "deposit",
                "withdrawal": "withdrawal",
                "cuenta bancaria": "bank_account"
            }, inplace=True)


            # Validar columnas requeridas
            required_columns = ["date", "reference_number", "description", "deposit", "withdrawal", "bank_account"]
            missing_columns = [col for col in required_columns if col not in transformed_data.columns]
            if missing_columns:
                frappe.throw(_("Faltan columnas en el archivo transformado: {0}").format(", ".join(missing_columns)))

            # Guardar archivo transformado como CSV
            out_file_name = f"transformed_{os.path.basename(file_path).replace('.xlsx', '.csv').replace('.xls', '.csv')}"
            output_file_path = os.path.join(
                frappe.utils.get_site_path("private", "files"),
                out_file_name
            )
            transformed_data.to_csv(output_file_path, index=False, encoding="utf-8", sep=",")
            self.log_steps.append(f"Archivo transformado guardado en: {output_file_path}")

            # Registrar archivo en el Doctype File
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_name": out_file_name,
                "file_url": f"/private/files/{out_file_name}",
                "is_private": 1
            })
            file_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            self.log_steps.append(f"Archivo registrado en Frappe con URL: {file_doc.file_url}")
            frappe.log_error(message=self.log_steps, title="Log de importación TRANS")

            # Retornar la URL del archivo registrado
            return file_doc.file_url
        except Exception as e:
            self.log_steps.append(f"Error durante la transformación del archivo: {str(e)}")
            frappe.log_error(message=self.log_steps, title="Log de importación")
            frappe.throw(_("Error al transformar el archivo: {0}").format(str(e)))

    def validate_header_row(self, header_row, bank_name):
        """Validar si se encontró el encabezado en el archivo"""
        if header_row is None:
            frappe.throw(
                _("No se encontró el encabezado esperado en el archivo para el banco {0}. "
                  "Por favor, verifique el archivo o el banco seleccionado.").format(bank_name)
            )

    def process_caixa(self, rows, bank_account_name):
        """Transformar archivo para CAIXA"""
        try:
            self.log_steps.append("Procesando archivo CAIXA")
            
            # Verificar si `rows` ya es un DataFrame
            if isinstance(rows, pd.DataFrame):
                df = rows.copy()
            else:
                # Convertir filas en DataFrame
                df = pd.DataFrame(rows)

            # Buscar encabezado
            header_row = None
            for i, row in df.iterrows():
                if "Fecha" in row.values and "Fecha valor" in row.values and "Movimiento" in row.values:
                    header_row = i
                    break

            if header_row is None:
                frappe.throw(_("No se encontró el encabezado esperado en el archivo para CAIXA."))

            # Cargar los datos a partir del encabezado
            df.columns = df.iloc[header_row]  # Asignar nombres de columnas desde el encabezado detectado
            df = df.iloc[header_row + 1:].reset_index(drop=True)  # Filtrar filas a partir del encabezado

            # Matchear y mapear las columnas según especificaciones
            df["Referencia"] = df.apply(
                lambda row: row["Movimiento"] if pd.notna(row["Movimiento"]) else "Sin referencia", axis=1
            )
            df["Descripción"] = df.apply(
                lambda row: row["Más datos"] if pd.notna(row["Más datos"]) else "Sin descripción", axis=1
            )
            df["Deposit"] = df["Importe"].apply(lambda x: float(x) if float(x) > 0 else 0)
            df["Withdrawal"] = df["Importe"].apply(lambda x: abs(float(x)) if float(x) < 0 else 0)
            df["Cuenta Bancaria"] = bank_account_name

            # Seleccionar y reorganizar las columnas necesarias
            processed_data = df[
                ["Fecha valor", "Referencia", "Descripción", "Deposit", "Withdrawal", "Cuenta Bancaria"]
            ]

            # Filtrar por la fecha más reciente en Bank Transaction
            latest_transaction_date = get_latest_bank_transaction_date(bank_account_name)
            if latest_transaction_date:
                self.log_steps.append(f"Filtrando transacciones desde: {latest_transaction_date}")
                processed_data = processed_data[
                    pd.to_datetime(processed_data["Fecha valor"], errors="coerce") >= pd.to_datetime(latest_transaction_date)
                ]
            
            self.log_steps.append("Datos procesados para CAIXA.")
            frappe.log_error(message=processed_data.to_string(), title="Log de archivo CAIXA")
            return processed_data
        except Exception as e:
            frappe.throw(_("Error al procesar archivo CAIXA: {0}").format(str(e)))


    def process_santander(self, rows, bank_account_name):
        """Transformar archivo para Santander"""
        try:
            self.log_steps.append("Procesando archivo Santander")

            # Verificar si `rows` ya es un DataFrame
            if isinstance(rows, pd.DataFrame):
                df = rows.copy()
            else:
                df = pd.DataFrame(rows[1:], columns=rows[0])

            # Buscar encabezado
            header_row = None
            for i, row in df.iterrows():
                if "Fecha Operación" in row.values or "Fecha Valor" in row.values:
                    header_row = i
                    break

            self.validate_header_row(header_row, "SANTANDER")

            # Leer desde el encabezado
            df.columns = df.iloc[header_row]  # Nombres de las columnas desde el encabezado detectado
            df = df.iloc[header_row + 1:].reset_index(drop=True)

            # Matchear y mapear las columnas según especificaciones
            df["Referencia"] = df.apply(
                lambda row: row["Referencia 1"] if pd.notna(row["Referencia 1"]) else row["Referencia 2"], axis=1
            )
            df["Descripción"] = df["Concepto"] if "Concepto" in df.columns else "Sin descripción"
            df["Deposit"] = df["Importe"].apply(lambda x: float(x) if float(x) > 0 else 0)
            df["Withdrawal"] = df["Importe"].apply(lambda x: abs(float(x)) if float(x) < 0 else 0)
            df["Cuenta Bancaria"] = bank_account_name

            # Seleccionar y reorganizar las columnas necesarias
            processed_data = df[
                ["Fecha Valor", "Referencia", "Descripción", "Deposit", "Withdrawal", "Cuenta Bancaria"]
            ]

            # Filtrar por la fecha más reciente en Bank Transaction
            latest_transaction_date = get_latest_bank_transaction_date(bank_account_name)
            if latest_transaction_date:
                self.log_steps.append(f"Filtrando transacciones desde: {latest_transaction_date}")
                processed_data = processed_data[
                    pd.to_datetime(processed_data["Fecha Valor"], errors="coerce") >= pd.to_datetime(latest_transaction_date)
                ]
            
            self.log_steps.append("Datos procesados para Santander.")
            frappe.log_error(message=processed_data.to_string(), title="Log de archivo Santander")
            return processed_data
        except Exception as e:
            frappe.throw(_("Error al procesar archivo Santander: {0}").format(str(e)))


    def process_ibercaja(self, rows, bank_account_name):
        """Transformar archivo para Ibercaja"""
        try:
            self.log_steps.append("Procesando archivo Ibercaja")

            # Verificar si `rows` ya es un DataFrame
            if isinstance(rows, pd.DataFrame):
                df = rows.copy()
            else:
                df = pd.DataFrame(rows[1:], columns=rows[0])

            # Buscar encabezado
            header_row = None
            for i, row in df.iterrows():
                if "Fecha Oper" in row.values or "Fecha Valor" in row.values:
                    header_row = i
                    break

            self.validate_header_row(header_row, "IBERCAJA")

            # Leer desde el encabezado
            df.columns = df.iloc[header_row]  # Nombres de las columnas desde el encabezado detectado
            df = df.iloc[header_row + 1:].reset_index(drop=True)

            # Matchear y mapear las columnas según especificaciones
            df["Referencia"] = df.apply(
                lambda row: row["Referencia"] if pd.notna(row["Referencia"]) else row["Concepto"], axis=1
            )
            df["Descripción"] = df["Descripción"] if "Descripción" in df.columns else "Sin descripción"
            df["Deposit"] = df["Importe"].apply(lambda x: float(x) if float(x) > 0 else 0)
            df["Withdrawal"] = df["Importe"].apply(lambda x: abs(float(x)) if float(x) < 0 else 0)
            df["Cuenta Bancaria"] = bank_account_name

            # Seleccionar y reorganizar las columnas necesarias
            processed_data = df[
                ["Fecha Valor", "Referencia", "Descripción", "Deposit", "Withdrawal", "Cuenta Bancaria"]
            ]

            # Filtrar por la fecha más reciente en Bank Transaction
            latest_transaction_date = get_latest_bank_transaction_date(bank_account_name)
            if latest_transaction_date:
                self.log_steps.append(f"Filtrando transacciones desde: {latest_transaction_date}")
                processed_data = processed_data[
                    pd.to_datetime(processed_data["Fecha Valor"], errors="coerce") >= pd.to_datetime(latest_transaction_date)
                ]
            
            self.log_steps.append("Datos procesados para Ibercaja.")
            frappe.log_error(message=processed_data.to_string(), title="Log de archivo Ibercaja")
            return processed_data
        except Exception as e:
            frappe.throw(_("Error al procesar archivo Ibercaja: {0}").format(str(e)))


@frappe.whitelist()
def get_preview_from_template(data_import, import_file=None, google_sheets_url=None):
    """Interceptar el preprocesamiento antes de la previsualización"""
    log_steps = []
    log_steps.append("Interceptando get_preview_from_template")
    

    # Obtener la instancia de "Bank Statement Import"
    doc = frappe.get_doc("Bank Statement Import", data_import)
    log_steps.append(f"Instancia obtenida: {doc}")
    # Procesar el archivo antes de generar la previsualización
    file_path = import_file or doc.import_file
    if not file_path:
        frappe.throw(_("Debe seleccionar un archivo para importar."))
    log_steps.append(f"Archivo seleccionado: {file_path}")
    # Obtener el banco desde la cuenta bancaria
    bank_account = frappe.get_doc("Bank Account", doc.bank_account)
    if not bank_account.bank:
        frappe.throw(_("La cuenta bancaria seleccionada no tiene un banco asociado."))
    log_steps.append(f"Cuenta bancaria seleccionada: {bank_account.bank}")
    bank = frappe.get_doc("Bank", bank_account.bank)
    log_steps.append(f"Banco detectado: {bank.bank_name}")

    # Transformar el archivo
    processed_file_path = doc.transform_file(file_path, bank, doc.bank_account)
    log_steps.append(f"Archivo transformado para previsualización: {processed_file_path}")


    file_name = frappe.db.get_value("File", {"file_url": processed_file_path})
    log_steps.append(f"Archivo registrado en Frappe con URL: {file_name}")

    frappe.log_error(message=log_steps, title="Log de importación_whitelist")

    # Llamar al flujo original con el archivo transformado
    return frappe.get_doc("Bank Statement Import", data_import).get_preview_from_template(
        import_file=processed_file_path, google_sheets_url=google_sheets_url
    )


def get_latest_bank_transaction_date(bank_account_name):
    """Obtener la fecha más reciente de una transacción bancaria validada para la cuenta bancaria dada."""
    latest_transaction = frappe.db.get_value(
        "Bank Transaction",
        {"bank_account": bank_account_name, "docstatus": 1},
        "MAX(date)",
    )
    return latest_transaction