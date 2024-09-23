import frappe
from frappe.utils.background_jobs import enqueue
from frappe.utils.xlsxutils import handle_html
import json
import csv
import re
from erpnext.accounts.doctype.bank_statement_import.bank_statement_import import BankStatementImport


# Override de la clase BankStatementImport para evitar que se pida la columna "Bank Account" en el archivo
class CustomBankStatementImport(BankStatementImport):
    def start_import(self):
        # Obtén la previsualización del template
        preview = self.get_preview_from_template(self.import_file, self.google_sheets_url)

        # En vez de validar que el archivo tenga la columna "Bank Account", tomamos la cuenta del documento
        if not self.bank_account:
            frappe.throw(_("Please select a Bank Account in the import tool before proceeding."))

        # No verificamos si la columna 'Bank Account' está en los datos del archivo
        from frappe.utils.background_jobs import is_job_enqueued
        from frappe.utils.scheduler import is_scheduler_inactive

        if is_scheduler_inactive() and not frappe.flags.in_test:
            frappe.throw(_("Scheduler is inactive. Cannot import data."), title=_("Scheduler Inactive"))

        job_id = f"bank_statement_import::{self.name}"
        if not is_job_enqueued(job_id):
            enqueue(
                start_custom_import,  # Cambiamos la función de importación al override
                queue="default",
                timeout=6000,
                event="data_import",
                job_id=job_id,
                data_import=self.name,
                bank_account=self.bank_account,
                import_file_path=self.import_file,
                google_sheets_url=self.google_sheets_url,
                bank=self.bank,
                template_options=self.template_options,
                now=frappe.conf.developer_mode or frappe.flags.in_test,
            )
            return True

        return False

# Override de la función start_import para agregar la cuenta bancaria seleccionada
def start_custom_import(data_import, bank_account, import_file_path, google_sheets_url, bank, template_options):
    """Este método corre en segundo plano"""

    update_mapping_db(bank, template_options)

    data_import = frappe.get_doc("Bank Statement Import", data_import)
    file = import_file_path if import_file_path else google_sheets_url

    import_file = ImportFile("Bank Transaction", file=file, import_type="Insert New Records")

    data = parse_data_from_template(import_file.raw_data)
    # Agrega la cuenta bancaria a las filas de datos sin requerir que esté en el archivo
    add_bank_account(data, bank_account)

    # Importar datos usando el Importer
    try:
        i = Importer(data_import.reference_doctype, data_import=data_import)
        i.import_data()
    except Exception as e:
        frappe.db.rollback()
        data_import.db_set("status", "Error")
        data_import.log_error(f"Bank Statement Import failed: {str(e)}")
    finally:
        frappe.flags.in_import = False

    frappe.publish_realtime("data_import_refresh", {"data_import": data_import.name})

# Función que agrega la cuenta bancaria automáticamente a las filas de datos
def add_bank_account(data, bank_account):
    bank_account_loc = None
    if "Bank Account" not in data[0]:
        data[0].append("Bank Account")  # Si no está la columna, la agregamos
    else:
        for loc, header in enumerate(data[0]):
            if header == "Bank Account":
                bank_account_loc = loc

    for row in data[1:]:
        if bank_account_loc:
            row[bank_account_loc] = bank_account  # Asignamos el valor de la cuenta bancaria en la posición correspondiente
        else:
            row.append(bank_account)  # Si no existe la columna, la agregamos al final de cada fila

# Asegurarse de actualizar el mapping de columnas con el nuevo formato
def update_mapping_db(bank, template_options):
    bank = frappe.get_doc("Bank", bank)
    for d in bank.bank_transaction_mapping:
        d.delete()

    for d in json.loads(template_options)["column_to_field_map"].items():
        bank.append("bank_transaction_mapping", {"bank_transaction_field": d[1], "file_field": d[0]})

    bank.save()

# Reutilizamos el resto de funciones sin cambios
