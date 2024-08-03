import frappe
import requests
from frappe import _

def get_encrypted_password(doctype, name, fieldname='password', raise_exception=True):
    auth = frappe.db.sql('''select `password` from `__Auth`
        where doctype=%(doctype)s and name=%(name)s and fieldname=%(fieldname)s''',
        { 'doctype': doctype, 'name': name, 'fieldname': fieldname })

    if auth and auth[0][0]:
        return auth[0][0]
    elif raise_exception:
        frappe.throw(_('Password not found'), frappe.AuthenticationError)

def create_user_in_crm(doc, method):
    # Comprobar si el usuario tiene el rol "Usuario de portal CRM"
    user_roles = [role.role for role in doc.roles]
    if "Usuario de portal CRM" not in user_roles:
        if doc.crm_user_created:
            # Restablecer el campo crm_user_created a 0 si el usuario no tiene el rol requerido
            doc.db_set('crm_user_created', 0)
        return

    # Verificar si el usuario ya ha sido creado en CRM
    if doc.crm_user_created:
        return

    # Intentar obtener la contraseña encriptada usando get_encrypted_password
    try:
        encrypted_password = get_encrypted_password('User', doc.name, 'password')
    except Exception as e:
        frappe.log_error(message=str(e), title="Error al obtener la contraseña encriptada")

    if not encrypted_password:
        frappe.log_error(message="No se pudo obtener la contraseña encriptada", title="Error al obtener la contraseña encriptada")
    else:
        frappe.log_error(message=f"Contraseña encriptada: {encrypted_password}", title="Contraseña encriptada")

    # Crear el payload para la solicitud POST para crear el usuario con el Role Profile
    payload = {
        "email": doc.email,
        "first_name": doc.first_name,
        "last_name": doc.last_name,
        "username": doc.username,
        "role_profile_name": "Principal"
    }

    # URL del CRM
    crm_url = "https://crm.grupoatu.com/api/resource/User"

    # Encabezados para la solicitud
    headers = {
        "Content-Type": "application/json",
        "Authorization": "token 565da94061d98f1:4182b2cbe6de514"
    }

    # Realizar la solicitud POST al CRM para crear el usuario
    response = requests.post(crm_url, json=payload, headers=headers)

    # Manejar la respuesta del CRM para la creación del usuario
    if response.status_code != 200:
        frappe.log_error(f"Error al crear usuario en CRM: {response.json().get('message')}")

    # Añadir la contraseña encriptada al usuario en el CRM
    try:
        user_name = response.json().get('data').get('name')
        password_payload = {
            "user_name": user_name,
            "encrypted_password": encrypted_password
        }
        password_url = "https://crm.grupoatu.com/api/method/crm.api.set_user_password.set_user_password"
        password_response = requests.post(password_url, json=password_payload, headers=headers)

        if password_response.status_code != 200:
            frappe.log_error(f"Error al establecer la contraseña en CRM: {password_response.json().get('message')}")
        else:
            frappe.msgprint(_("Usuario creado en CRM con contraseña"), title="Crear usuario en CRM")
            
            # Marcar el usuario como creado en CRM
            doc.db_set('crm_user_created', 1)
    except Exception as e:
        frappe.log_error(message=str(e), title="Error al establecer la contraseña en CRM")
        frappe.throw("No se pudo establecer la contraseña encriptada del usuario en el CRM.")
