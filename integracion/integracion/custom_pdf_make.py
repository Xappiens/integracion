import frappe
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file

@frappe.whitelist()
def custom_download_and_attach_pdf(doctype, name, format=None, doc=None, no_letterhead=0, language=None, letterhead=None):
    doc = doc or frappe.get_doc(doctype, name)
    
    # Permite ignorar permisos temporalmente
    frappe.flags.ignore_permissions = True
    
    # Configura el idioma
    if language:
        frappe.local.lang = language
    
    # Genera el PDF
    pdf_file = frappe.get_print(
        doctype, name, format, doc=doc, as_pdf=True, letterhead=letterhead, no_letterhead=no_letterhead
    )
    
    # Guarda el archivo en el sistema de archivos y adjunta al documento
    file_name = f"{name.replace(' ', '-').replace('/', '-')}.pdf"
    saved_file = save_file(file_name, pdf_file, doctype, name, is_private=1)
    
    # Asegurarse de que el archivo esté completamente guardado antes de proceder
    frappe.db.commit()

    # Devuelve la URL del archivo adjunto
    return saved_file.file_url
