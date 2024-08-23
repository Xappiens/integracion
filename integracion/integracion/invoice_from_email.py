import frappe
import logging
from frappe.utils.file_manager import save_file
import random

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/purchase_email.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@frappe.whitelist()
def invoice_from_email(email_subject, email_content, email_from, attachments):
    logger.debug(f"Received email with subject: {email_subject}, from: {email_from}")
    
    if not attachments or not any(attachment.get('filename', '').lower().endswith('.pdf') for attachment in attachments):
        logger.error("El correo no contiene adjuntos PDF válidos.")
        return {"status": "error", "message": "Correo no válido. Debe contener al menos un archivo adjunto en formato PDF."}



    try:
        proveedor = frappe.get_all('Supplier', filters={'email_id': email_from}, fields=['name'])

        if not proveedor:
            logger.error(f"Proveedor no encontrado para el email: {email_from}")
            proveedor_name = "BURGOS ATU, S.L."
        else:
            proveedor_name = proveedor[0]['name']

        logger.debug(f"Proveedor final: {proveedor_name}")

        supplier_doc = frappe.get_doc('Supplier', proveedor_name)
        debit_to_account = None

        if supplier_doc.accounts:
            for account in supplier_doc.accounts:
                if account.company == 'Academia Técnica Universitaria SL':
                    debit_to_account = account.account
                    break

        if not debit_to_account:
            cuentas = frappe.get_all('Account', filters={'company': 'Academia Técnica Universitaria SL'}, fields=['name'])
            for cuenta in cuentas:
                account_name_parts = cuenta['name'].split(' - ')
                if len(account_name_parts) > 1 and proveedor_name in account_name_parts:
                    debit_to_account = cuenta['name']
                    break

        
        if not debit_to_account:
            logger.error(f"No se encontró la cuenta contable para el proveedor: {proveedor_name} y la empresa: Academia Tecnica Universitaria SL")
            return {"status": "error", "message": "No se encontró la cuenta contable para la empresa y proveedor especificados."}

        random_number = random.randint(1000, 9999)
        bill_no = f"{proveedor_name}_{random_number}"

        invoice = frappe.get_doc({
            'doctype': 'Purchase Invoice',
            'supplier': proveedor_name,
            'company': 'Academia Técnica Universitaria SL',
            'bill_no': bill_no,
            'debit_to': debit_to_account,
            'custom_procedente': email_from,
            'custom_proc_email' : 1,
            'items': [{
                'item_name': 'Default',
                'qty': 1,
                'rate': 0,
                'expense_account': '62900080 - OTROS GASTOS - ATUSL'
            }]
        })

        invoice.insert()
        logger.debug(f"Factura de compra creada: {invoice.name}")
        
        # Manejar múltiples adjuntos
        if attachments:
            for attachment in attachments:
                if attachment.get('filename') and attachment.get('content'):
                    file_doc = save_file(attachment['filename'], attachment['content'], 'Purchase Invoice', invoice.name, is_private=True)
                    invoice.add_comment("Attachment", file_doc.file_url)
                    logger.debug(f"Archivo adjunto guardado: {file_doc.file_url}")

        invoice.save()
        frappe.db.commit()
        logger.info(f"Factura guardada y transacción commitida: {invoice.name}")

        return {"status": "success", "message": "Factura creada exitosamente.", "invoice_name": invoice.name}

    except Exception as e:
        logger.exception(f"Error al manejar el correo: {str(e)}")
        return {"status": "error", "message": str(e)}
