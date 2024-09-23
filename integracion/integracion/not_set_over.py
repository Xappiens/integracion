import frappe

def force_disable_user(doc, method):
    current_user = frappe.session.user

    # Verificar si el usuario actual tiene el rol 'Accounts User'
    if "Accounts User" in frappe.get_roles(current_user):
        # Obtener el valor actual de 'enabled' antes del cambio
        current_enabled_value = frappe.db.get_value("User", doc.name, "enabled")

        # Si el valor actual es 1 (usuario habilitado) y lo están deshabilitando (doc.enabled = 0)
        if current_enabled_value == 1 and doc.enabled == 0:
            # Forzar la deshabilitación directamente en la base de datos
            frappe.db.set_value("User", doc.name, "enabled", 0)
            frappe.db.commit()

        if current_enabled_value == 0 and doc.enabled == 1:
            # Forzar la deshabilitación directamente en la base de datos
            frappe.db.set_value("User", doc.name, "enabled", 1)
            frappe.db.commit()

