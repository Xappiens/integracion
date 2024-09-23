import frappe

def job_offer_query(user):
    # Verificar si el usuario tiene el rol "Asesoría" directamente en la base de datos
    has_asesoria_role = frappe.db.exists('Has Role', {'parent': user, 'role': 'Asesoría'})
    
    # Si el usuario tiene el rol "Asesoría", aplicar el filtro
    if has_asesoria_role:
        return "`tabJob Offer`.docstatus = 1"

    return ""
