import frappe
from frappe import _

def get_data(data):
    return {
        "fieldname": "custom_plan",  # Campo en Planes Formativos que conecta con Program, Course, etc.
        "transactions": [
            {
                "label": _("Educación"),
                "items": ["Program", "Course", "Student Group"]
            }
        ]
    }

@frappe.whitelist()
def add_purchase_invoices_to_dashboard(plan_name):
    # Consulta para obtener las facturas de compra relacionadas desde la tabla hija 'Porcentaje Factura'
    facturas_compra = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabPorcentaje Factura`
        WHERE `plan` = %s AND parenttype = 'Purchase Invoice'
    """, (plan_name,), as_dict=True)

    # Consulta para obtener las facturas de venta relacionadas desde la tabla hija 'Porcentaje Factura'
    facturas_venta = frappe.db.sql("""
        SELECT DISTINCT parent
        FROM `tabPorcentaje Factura`
        WHERE `plan` = %s AND parenttype = 'Sales Invoice'
    """, (plan_name,), as_dict=True)

    # Si no hay facturas de compra ni de venta, retornamos un mensaje indicando que no existen facturas relacionadas
    if not facturas_compra and not facturas_venta:
        return "<p>No hay facturas relacionadas.</p>"

    # Construimos la lista de facturas de compra
    factura_compra_links = "<ul>"
    for factura in facturas_compra:
        factura_compra_links += f"<li><a href='/app/purchase-invoice/{factura['parent']}' target='_blank'>{factura['parent']}</a></li>"
    factura_compra_links += "</ul>"

    # Construimos la lista de facturas de venta
    factura_venta_links = "<ul>"
    for factura in facturas_venta:
        factura_venta_links += f"<li><a href='/app/sales-invoice/{factura['parent']}' target='_blank'>{factura['parent']}</a></li>"
    factura_venta_links += "</ul>"

    # Retornamos dos listas con los resultados
    return f"""
        <div style='display: flex; justify-content: space-around;'>
            <div>
                <h5>Facturas de Compra Relacionadas:</h5>
                {factura_compra_links}
            </div>
            <div>
                <h5>Facturas de Venta Relacionadas:</h5>
                {factura_venta_links}
            </div>
        </div>
    """

@frappe.whitelist()
def add_instructor_to_dashboard(plan_name):
    # Obtener los expedientes relacionados con el plan formativo
    expedientes = frappe.get_all("Program", filters={"custom_Plan": plan_name}, fields=["name"])
    
    instructores = []
    
    for expediente in expedientes:
        # Obtener los instructores relacionados con cada expediente
        instructores_encontrados = frappe.db.sql("""
            SELECT DISTINCT parent
            FROM `tabInstructor Log`
            WHERE program = %s AND parenttype = 'Instructor'
        """, (expediente.name,), as_dict=True)
        
        # Añadir los instructores encontrados a la lista
        for instructor in instructores_encontrados:
            instructores.append(instructor['parent'])
    
    # Si no hay instructores, retornar un mensaje
    if not instructores:
        return "<p>No hay instructores relacionados.</p>"
    
    # Construir una lista HTML con enlaces a los instructores
    instructor_links = "<h5>Instructores Relacionados:</h5><ul>"
    for instructor in instructores:
        instructor_links += f"<li><a href='/app/instructor/{instructor}' target='_blank'>{instructor}</a></li>"
    instructor_links += "</ul>"
    
    # Retornar el HTML con los enlaces
    return instructor_links

                      