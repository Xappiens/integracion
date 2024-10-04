import frappe
from frappe.utils.background_jobs import enqueue
from frappe.utils.xlsxutils import handle_html

import csv
import json
import re
import openpyxl
from frappe import _
from frappe.core.doctype.data_import.data_import import DataImport
from frappe.core.doctype.data_import.importer import Importer, ImportFile
from frappe.utils.background_jobs import enqueue
from frappe.utils.xlsxutils import ILLEGAL_CHARACTERS_RE, handle_html
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from erpnext.accounts.doctype.bank_statement_import.bank_statement_import import BankStatementImport

INVALID_VALUES = ("", None)


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
def parse_data_from_template(raw_data):
	data = []

	for _i, row in enumerate(raw_data):
		if all(v in INVALID_VALUES for v in row):
			# empty row
			continue

		data.append(row)

	return data

# Reutilizamos el resto de funciones sin cambios


@frappe.whitelist()
def reconcile_vouchers(bank_transaction_name, vouchers):
    # Parseamos los vouchers
    vouchers = json.loads(vouchers)
    
    # Obtenemos la transacción bancaria actual
    transaction = frappe.get_doc("Bank Transaction", bank_transaction_name)
    
    # Conciliamos la transacción actual
    transaction.add_payment_entries(vouchers)
    transaction.validate_duplicate_references()
    transaction.allocate_payment_entries()
    transaction.update_allocated_amount()
    transaction.set_status()
    transaction.save()
    
    # Verificamos si la cuenta seleccionada al crear el asiento tiene una cuenta bancaria asociada,
    # y que sea diferente de la cuenta bancaria de la transacción actual
    related_bank_account = find_related_bank_account(vouchers, transaction.bank_account)

    # Si existe una cuenta bancaria relacionada, la usamos para buscar la transacción opuesta
    if related_bank_account:
        frappe.msgprint(f"Cuenta bancaria relacionada encontrada: {related_bank_account}")
        opposite_transaction_name = find_opposite_transaction(transaction, related_bank_account)
    else:
        # Si no hay cuenta bancaria relacionada, buscamos la transacción opuesta con las cuentas y montos
        frappe.msgprint("No se encontró cuenta bancaria relacionada. Buscando transacción opuesta basada en cuentas y montos.")
        opposite_transaction_name = find_opposite_transaction(transaction)

    # Si se encuentra la transacción opuesta, la conciliamos automáticamente con el mismo asiento contable
    if opposite_transaction_name:
        opposite_transaction = frappe.get_doc("Bank Transaction", opposite_transaction_name)
        opposite_transaction.add_payment_entries(vouchers)
        opposite_transaction.validate_duplicate_references()
        opposite_transaction.allocate_payment_entries()
        opposite_transaction.update_allocated_amount()
        opposite_transaction.set_status()
        opposite_transaction.save()

    return transaction

def find_related_bank_account(vouchers, current_bank_account):
    """Verifica si la cuenta contable seleccionada en los vouchers tiene una cuenta bancaria asociada
    y que sea diferente a la cuenta bancaria actual de la transacción."""
    related_bank_account = None
    for voucher in vouchers:
        account_name = voucher.get('account')  # Obtenemos el nombre de la cuenta contable seleccionada
        # Verificamos si esa cuenta contable tiene una cuenta bancaria relacionada
        related_bank_account = frappe.db.get_value("Bank Account", {"account": account_name}, "name")
        
        # Verificamos si la cuenta bancaria relacionada es diferente de la cuenta bancaria actual
        if related_bank_account and related_bank_account != current_bank_account:
            break  # Si encontramos una cuenta bancaria diferente, salimos del bucle
        else:
            related_bank_account = None  # Si la cuenta bancaria es la misma, no la usamos

    return related_bank_account

def find_opposite_transaction(transaction, related_bank_account=None):
    """Buscar la transacción bancaria opuesta basada en el monto y la fecha de referencia"""
    
    # Determinamos si estamos buscando un ingreso o una retirada como transacción opuesta
    opposite_type = "Deposit" if transaction.withdrawal > 0 else "Withdrawal"
    
    # Si tenemos una cuenta bancaria relacionada, la usamos para buscar la transacción opuesta
    if related_bank_account:
        opposite_transaction = frappe.db.get_value(
            "Bank Transaction",
            {
                "bank_account": related_bank_account,  # Usamos la cuenta bancaria relacionada
                opposite_type.lower(): abs(transaction.withdrawal) if transaction.withdrawal > 0 else abs(transaction.deposit),  # Mismo monto pero opuesto
                "cheque_date": transaction.cheque_date  # Usamos la fecha de cheque como referencia
            },
            "name"
        )
    else:
        # Si no tenemos una cuenta bancaria relacionada, buscamos basada en las cuentas y montos
        opposite_transaction = frappe.db.get_value(
            "Bank Transaction",
            {
                "bank_account": ["!=", transaction.bank_account],  # Cuenta bancaria diferente
                opposite_type.lower(): abs(transaction.withdrawal) if transaction.withdrawal > 0 else abs(transaction.deposit),  # Mismo monto pero opuesto
                "cheque_date": ["between", transaction.cheque_date - timedelta(days=1), transaction.cheque_date + timedelta(days=1)]  # Fecha cercana
            },
            "name"
        )
    
    return opposite_transaction
