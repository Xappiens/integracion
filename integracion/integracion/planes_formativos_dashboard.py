import frappe
from frappe import _

def get_data(data):
    return {
        "fieldname": "custom_plan",  # Campo en Planes Formativos que conecta con Program, Course, etc.
        "transactions": [
            {
                "label": _("Educación"),
                "items": ["Program", "Course", "Student Group"]  # Conexiones ya existentes
            },
            {
                "label": _("Facturación"),
                "items": get_related_purchase_invoices(data.name)  # Se realiza una consulta manual para obtener las facturas
            }
        ]
    }

def get_related_purchase_invoices(plan_name):
    # Consulta para obtener las facturas relacionadas desde la tabla hija 'Porcentaje Factura'
    facturas = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabPorcentaje Factura`
        WHERE `plan` = %s
    """, (plan_name,), as_dict=True)

    # Log para depuración con la cantidad de facturas encontradas
    frappe.log_error(f"Facturas encontradas: {len(facturas)}", "Depuración de Facturas")

    # Si no hay facturas, devolvemos un texto que indique que no existen
    if not facturas:
        return ["No Related Purchase Invoices"]  # Retornamos una cadena que indique que no hay facturas

    # Si hay facturas, retornamos los nombres de las facturas de compra relacionadas
    return [factura['parent'] for factura in facturas]
