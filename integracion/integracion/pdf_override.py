# import frappe
# import logging
# from frappe.utils.pdf import get_pdf
# from frappe.utils.file_manager import save_file
# from frappe.utils.print_format import download_pdf as original_download_pdf
# from logging.handlers import RotatingFileHandler

# # Configurar el logger
# logger = logging.getLogger(__name__)
# handler = RotatingFileHandler(
#     '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/on_print.log',
#     maxBytes=5 * 1024 * 1024,  # 5 MB
#     backupCount=3  # Mantener hasta 3 archivos de log antiguos
# )
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)
# logger.setLevel(logging.INFO)

# @frappe.whitelist()
# def capture_print_event(doctype, docname):
#     logger.info(f"Evento de impresión capturado para {doctype} {docname}")

#     # Generar el PDF
#     pdf_content = frappe.get_print(doctype, docname, as_pdf=True)

#     # Guardar el PDF como un archivo adjunto
#     file_name = f"{docname}.pdf"
#     logger.info(f"Guardando el archivo {file_name}")
#     save_file(file_name, pdf_content, doctype, docname, is_private=True)

#     logger.info(f"Archivo adjunto correctamente al documento {doctype} {docname}")
