import frappe

def job_offer_query(user):
    # Verificar si el usuario tiene el rol "Asesoría" directamente en la base de datos
    has_asesoria_role = frappe.db.exists('Has Role', {'parent': user, 'role': 'Asesoría'})
    
    # Si el usuario tiene el rol "Asesoría", aplicar el filtro
    if has_asesoria_role:
        return "`tabJob Offer`.docstatus = 1"

    return ""

def user_query(user):
    # Verificar si el usuario tiene el Role Profile 'Base'
    role_profile = frappe.db.get_value('User', user, 'role_profile_name')

    if role_profile == 'Base':
        # Si el usuario tiene el Role Profile 'Base', retornar una cadena que limite la vista a su propio usuario
        return f"name = '{user}'"
    else:
        # Si no tiene el Role Profile 'Base', retornar una cadena para excluir a 'Guest' y 'Administrator'
        return "name NOT IN ('Guest', 'Administrator') AND enabled = 1"
