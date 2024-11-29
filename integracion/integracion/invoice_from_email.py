import frappe
import logging
from frappe.utils.file_manager import save_file
import random
import base64
import PyPDF2
from io import BytesIO
from PyPDF2.errors import PdfReadError

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/purchase_email.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

@frappe.whitelist()
# def invoice_from_email(email_subject, email_content, email_from, attachments):
#     logger.debug(f"Received email with subject: {email_subject}, from: {email_from}")
    
#     # Filtrar y trabajar solo con archivos PDF
#     pdf_attachments = [attachment for attachment in attachments if attachment.get('filename', '').lower().endswith('.pdf')]
    
#     if not pdf_attachments:
#         logger.error("El correo no contiene adjuntos PDF válidos.")
#         return {"status": "error", "message": "Correo no válido. Debe contener al menos un archivo adjunto en formato PDF."}
#     else:
#         logger.debug(f"Found {len(pdf_attachments)} PDF attachments.")

#     try:
#         # Verificar que al menos uno de los PDFs contenga la palabra "factura"
#         keyword = "factura"
#         keyword_found = False

#         for attachment in pdf_attachments:
#             if attachment.get('filename') and attachment.get('content'):
#                 try:
#                     # Decodificar el contenido de Base64 a bytes
#                     attachment_content = base64.b64decode(attachment['content'])
#                     attachment_content = base64.b64decode(attachment_content)


#                     # Leer el contenido del PDF
#                     with BytesIO(attachment_content) as pdf_file:
#                         try:
#                             pdf_reader = PyPDF2.PdfReader(pdf_file)
#                             for page in pdf_reader.pages:
#                                 text = page.extract_text()
#                                 if keyword.lower() in text.lower():
#                                     keyword_found = True
#                                     break
#                         except PdfReadError as e:
#                             logger.error(f"Error leyendo el archivo PDF: {e}")
#                             return {"status": "error", "message": f"Error leyendo el archivo PDF: {e}"}

#                 except Exception as e:
#                     logger.error(f"Error decodificando o procesando el archivo adjunto: {e}")
#                     return {"status": "error", "message": f"Error procesando el archivo adjunto: {e}"}


#         # Continuar con la creación de la factura solo si se encuentra la palabra clave en algún PDF
#         proveedor = frappe.get_all('Supplier', filters={'email_id': email_from}, fields=['name'])

#         if not proveedor:
#             logger.error(f"Proveedor no encontrado para el email: {email_from}")
#             proveedor_name = "BURGOS ATU, S.L."
#         else:
#             proveedor_name = proveedor[0]['name']

#         logger.debug(f"Proveedor final: {proveedor_name}")

#         supplier_doc = frappe.get_doc('Supplier', proveedor_name)
#         debit_to_account = None

#         if supplier_doc.accounts:
#             for account in supplier_doc.accounts:
#                 if account.company == 'Academia Técnica Universitaria SL':
#                     debit_to_account = frappe.get_doc('Account', account.account)
#                     break

#         if not debit_to_account:
#             cuentas = frappe.get_all('Account', filters={'company': 'Academia Técnica Universitaria SL'}, fields=['name'])
#             for cuenta in cuentas:
#                 account_name_parts = cuenta['name'].split(' - ')
#                 if len(account_name_parts) > 1 and proveedor_name in account_name_parts:
#                     logger.debug(f"Cuenta contable encontrada: {cuenta}")
#                     debit_to_account = frappe.get_doc('Account', cuenta['name'])
#                     break

#         if not debit_to_account:
#             logger.error(f"No se encontró la cuenta contable para el proveedor: {proveedor_name} y la empresa: Academia Técnica Universitaria SL")
#             return {"status": "error", "message": "No se encontró la cuenta contable para la empresa y proveedor especificados."}

#         logger.debug(f"Cuenta contable encontrada: {debit_to_account} currency {debit_to_account.account_currency}")
#         random_number = random.randint(1000, 9999)
#         bill_no = f"{proveedor_name}_{random_number}"
#         currency = debit_to_account.account_currency or 'EUR'
#         if currency != 'EUR':
#             logger.error(f"La cuenta {debit_to_account.name} no tiene la misma moneda que el documento. Cuenta: {currency}, Documento: EUR.")
#             return {"status": "error", "message": "Conflicto de moneda entre la cuenta y el documento."}



#         invoice = frappe.get_doc({
#             'doctype': 'Purchase Invoice',
#             'supplier': proveedor_name,
#             'company': 'Academia Técnica Universitaria SL',
#             'bill_no': bill_no,
#             'debit_to': debit_to_account.name,
#             'currency': currency,
#             'party_account_currency': currency,
#             'custom_procedente': email_from,
#             'bill_date': frappe.utils.nowdate(),
#             'custom_proc_email': 1,
#             'items': [{
#                 'item_name': 'Default',
#                 'qty': 1,
#                 'rate': 0,
#                 'expense_account': '62900080 - OTROS GASTOS - ATUSL'
#             }]
#         })

#         frappe.flags.ignore_permissions = True
#         invoice.insert()
#         frappe.flags.ignore_permissions = False
#         logger.debug(f"Factura de compra creada: {invoice.name}")
        
#         # Manejar múltiples adjuntos (solo PDFs)
#         for attachment in pdf_attachments:
#             if attachment.get('filename') and attachment.get('content'):
#                 file_doc = save_file(attachment['filename'], attachment_content, 'Purchase Invoice', invoice.name, is_private=True)
#                 invoice.add_comment("Attachment", file_doc.file_url)
#                 logger.debug(f"Archivo adjunto guardado: {file_doc.file_url}")

#         invoice.save()
#         frappe.db.commit()
#         logger.info(f"Factura guardada y transacción commitida: {invoice.name}")

#         return {"status": "success", "message": "Factura creada exitosamente.", "invoice_name": invoice.name}

#     except Exception as e:
#         logger.exception(f"Error al manejar el correo: {str(e)}")
#         return {"status": "error", "message": str(e)}
