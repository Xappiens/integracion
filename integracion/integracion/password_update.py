# /home/frappe/frappe-bench/apps/integracion/integracion/auth_update.py

import frappe
import requests
from frappe import _

def get_current_encrypted_password(name, fieldname='password'):
    auth = frappe.db.sql('''SELECT `password` FROM `__Auth`
        WHERE doctype=%(doctype)s AND name=%(name)s AND fieldname=%(fieldname)s''',
        { 'doctype': 'User', 'name': name, 'fieldname': fieldname })

    if auth and auth[0][0]:
        return auth[0][0]
    return None

def update_password_in_crm(doc, method):
    # Obtener la contraseña actual encriptada de la base de datos
    current_encrypted_password = get_current_encrypted_password(doc.name, 'password')

    # Obtener la nueva contraseña encriptada
    new_encrypted_password = doc.password

    if new_encrypted_password and current_encrypted_password != new_encrypted_password:
        # Crear el payload para la solicitud POST
        payload = {
            "user_name": doc.name,
            "encrypted_password": new_encrypted_password
        }

        # URL del CRM
        password_url = "https://crm.grupoatu.com/api/method/crm.api.set_user_password.set_user_password"

        # Encabezados para la solicitud
        headers = {
            "Content-Type": "application/json",
            "Authorization": "token 565da94061d98f1:4182b2cbe6de514"
        }

        # Realizar la solicitud POST al CRM para actualizar la contraseña
        response = requests.post(password_url, json=payload, headers=headers)

        # Manejar la respuesta del CRM para la actualización de la contraseña
        if response.status_code != 200:
            frappe.throw(f"Error al actualizar la contraseña en CRM: {response.json().get('message')}")
        else:
            frappe.msgprint(_("Contraseña actualizada en CRM"), title="Actualizar contraseña en CRM")
            frappe.log_error(message="Contraseña actualizada en CRM", title="Actualizar contraseña en CRM")
    else:
        frappe.msgprint(_("La contraseña no ha cambiado"), title="Contraseña sin cambios")

