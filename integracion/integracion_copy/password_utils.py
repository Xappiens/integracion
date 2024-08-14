import requests
import frappe
from frappe import _

def get_encrypted_password(doctype, name, fieldname='password', raise_exception=True):
    auth = frappe.db.sql('''select `password` from `__Auth`
        where doctype=%(doctype)s and name=%(name)s and fieldname=%(fieldname)s''',
        {'doctype': doctype, 'name': name, 'fieldname': fieldname})

    if auth and auth[0][0]:
        return auth[0][0]
    elif raise_exception:
        frappe.throw(_('Password not found'), frappe.AuthenticationError)
    else:
        frappe.msgprint(_('User not created in CRM due to missing password'), alert=True)
        return None

def deactivate_user_in_crm(email):
    crm_url = "https://crm.grupoatu.com/api/resource/User"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "token 565da94061d98f1:4182b2cbe6de514"
    }

    response = requests.put(f"{crm_url}/{email}", json={"enabled": 0}, headers=headers)
    
    if response.status_code != 200:
        frappe.log_error(f"Error al desactivar usuario en CRM: {response.json().get('message')}")
    else:
        frappe.msgprint(_("Usuario desactivado en CRM"), title="Desactivar usuario en CRM")

def create_user_in_crm(doc, method):
    user_roles = [role.role for role in doc.roles]
    
    if "Usuario de portal CRM" not in user_roles:
        if doc.crm_user_created:
            doc.db_set('crm_user_created', 0)
            deactivate_user_in_crm(doc.email)
        return

    if doc.crm_user_created:
        return

    try:
        encrypted_password = get_encrypted_password('User', doc.name, 'password', raise_exception=False)
        if not encrypted_password:
            encrypted_password = ""
    except Exception as e:
        frappe.log_error(message=str(e), title="Error al obtener la contraseña encriptada")
        encrypted_password = ""

    payload = {
        "email": doc.email,
        "first_name": doc.first_name,
        "last_name": doc.last_name,
        "username": doc.username,
        "role_profile_name": "Principal"
    }

    crm_url = "https://crm.grupoatu.com/api/resource/User"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "token 565da94061d98f1:4182b2cbe6de514"
    }

    response = requests.post(crm_url, json=payload, headers=headers)

    if response.status_code == 409:  # User already exists
        get_user_response = requests.get(f"{crm_url}/{doc.email}", headers=headers)
        if get_user_response.status_code == 200:
            user_data = get_user_response.json().get('data')
            if not user_data.get('enabled'):
                enable_response = requests.put(f"{crm_url}/{doc.email}", json={"enabled": 1}, headers=headers)
                if enable_response.status_code == 200:
                    frappe.msgprint(_("Usuario existente en CRM fue habilitado"), title="Habilitar usuario en CRM")
                    doc.db_set('crm_user_created', 1)
                else:
                    frappe.log_error(f"Error al habilitar usuario en CRM: {enable_response.json().get('message')}")
            else:
                frappe.msgprint(_("El usuario ya existe en el CRM"), title="Usuario ya existe en CRM")
        else:
            frappe.log_error(f"Error al verificar existencia del usuario en CRM: {get_user_response.json().get('message')}")
    elif response.status_code != 200:
        frappe.log_error(f"Error al crear usuario en CRM: {response.json().get('message')}")
    else:
        try:
            if encrypted_password:
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
            else:
                frappe.msgprint(_("Usuario creado en CRM sin contraseña, se le pedirá que establezca una."), title="Crear usuario en CRM")

            doc.db_set('crm_user_created', 1)
        except Exception as e:
            frappe.log_error(message=str(e), title="Error al establecer la contraseña en CRM")
            frappe.throw("No se pudo establecer la contraseña encriptada del usuario en el CRM.")
