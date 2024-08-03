import frappe
from frappe.utils import nowdate, nowtime, now_datetime
import json

@frappe.whitelist(allow_guest=True)
def create_purchase_invoice():
    try:
        # Leer el JSON del cuerpo de la solicitud
        request_data = frappe.request.data
        if not request_data:
            frappe.response["status_code"] = 400
            frappe.response["status"] = "error"
            frappe.response["message"] = "Request data is empty"
            return

        data = json.loads(request_data)
        frappe.log_error(message=f"Datos del formulario: {data}", title="Debug: Datos del Formulario")

        # Verificar y extraer los datos necesarios del formulario
        due_date = data.get('due_date')
        items = data.get('items', [])
        attachments = data.get('attachments', [])

        if not due_date or not items:
            frappe.response["status_code"] = 400
            frappe.response["status"] = "error"
            frappe.response["message"] = "Missing required fields"
            return

        # Obtener la fecha y hora actuales
        posting_date = nowdate()
        posting_time = nowtime()

        # Generar el nombre del documento
        current_year = now_datetime().year
        last_name = frappe.db.sql("""SELECT name FROM `tabPurchase Invoice` WHERE name LIKE 'ACC-PINV-{}-%' ORDER BY name DESC LIMIT 1""".format(current_year))
        if last_name:
            last_number = int(re.search(r'\d+$', last_name[0][0]).group()) + 1
        else:
            last_number = 1
        new_name = "ACC-PINV-{}-{:05d}".format(current_year, last_number)

        # Crear la factura de compra directamente en la base de datos
        invoice_data = {
            'name': new_name,
            'title': 'Factura desde correo',
            'posting_date': posting_date,
            'posting_time': posting_time,
            'due_date': due_date
        }
        frappe.db.sql("""INSERT INTO `tabPurchase Invoice` (name, title, posting_date, posting_time, due_date)
                         VALUES (%(name)s, %(title)s, %(posting_date)s, %(posting_time)s, %(due_date)s)""", invoice_data)

        # Añadir artículos a la factura de compra
        for item in items:
            item_data = {
                'parent': new_name,
                'parentfield': 'items',
                'parenttype': 'Purchase Invoice',
                'item_code': item.get('item_code'),
                'qty': item.get('qty'),
                'rate': item.get('rate'),
                'amount': item.get('qty') * item.get('rate'),  # Calcular el monto
                'description': item.get('description', item.get('item_code')),  # Añadir descripción si está disponible
                'expense_account': item.get('expense_account')  # Añadir la cuenta de gastos si está disponible
            }
            frappe.db.sql("""INSERT INTO `tabPurchase Invoice Item` (parent, parentfield, parenttype, item_code, qty, rate, amount, description, expense_account)
                             VALUES (%(parent)s, %(parentfield)s, %(parenttype)s, %(item_code)s, %(qty)s, %(rate)s, %(amount)s, %(description)s, %(expense_account)s)""", item_data)

        # Añadir archivos adjuntos si existen
        for attachment in attachments:
            attachment_data = {
                'file_name': attachment['file_name'],
                'file_url': attachment['file_url'],
                'attached_to_doctype': 'Purchase Invoice',
                'attached_to_name': new_name
            }
            frappe.db.sql("""INSERT INTO `tabFile` (file_name, file_url, attached_to_doctype, attached_to_name)
                             VALUES (%(file_name)s, %(file_url)s, %(attached_to_doctype)s, %(attached_to_name)s)""", attachment_data)

        frappe.db.commit()
        frappe.log_error(message="Purchase Invoice insertado en la BD", title="Debug: Invoice Inserted")

        # Enviar respuesta
        frappe.response["status_code"] = 201
        frappe.response["status"] = "success"
        frappe.response["message"] = "Purchase Invoice created"
        frappe.response["name"] = new_name
    except json.JSONDecodeError:
        frappe.response["status_code"] = 400
        frappe.response["status"] = "error"
        frappe.response["message"] = "Invalid JSON data"
    except Exception as e:
        frappe.log_error(message=str(e), title="Purchase Invoice Creation Failed")
        frappe.response["status_code"] = 500
        frappe.response["status"] = "error"
        frappe.response["message"] = "An error occurred while creating the Purchase Invoice"
        frappe.response["error"] = str(e)
        frappe.log_error(message=f"Error al crear la factura de compra: {str(e)}", title="Debug: Exception")
