import frappe
from frappe import _

form_grid_templates = {"items": "templates/form_grid/item_grid.html"}

def notify_on_assign(doc, method):
    frappe.log_error(f"Asignación ejecutada para: {doc.allocated_to}", "Notificación")
    
    if doc.allocated_to:
        user = doc.allocated_to
        document_link = frappe.utils.get_url_to_form(doc.reference_type, doc.reference_name)

        reference_type_es = _(doc.reference_type)
        
        # Publicar evento de notificación en tiempo real (sin usar "message" y con un diccionario directamente)
        frappe.publish_realtime(
            "show_notification",
            {"message": f"Se te ha asignado un nuevo documento: {reference_type_es}", "link": document_link},
            user=user
        )


def copy_attachments_from_sales_order(doc, method):
    # Recorremos los items de la factura
    for item in doc.items:
        # Obtener la orden de venta desde el campo sales_order
        sales_order_name = item.sales_order
        if sales_order_name:
            # Obtener adjuntos de la orden de venta
            attachments = frappe.get_all("File", filters={
                "attached_to_doctype": "Sales Order",
                "attached_to_name": sales_order_name
            }, fields=["name", "file_name", "file_url", "is_private"])

            # Copiar cada adjunto a la nueva factura
            for attachment in attachments:
                new_attachment = frappe.get_doc({
                    "doctype": "File",
                    "file_url": attachment.file_url,
                    "file_name": attachment.file_name,
                    "attached_to_doctype": "Sales Invoice",
                    "attached_to_name": doc.name,
                    "is_private": attachment.is_private
                })
                new_attachment.insert(ignore_permissions=True)
