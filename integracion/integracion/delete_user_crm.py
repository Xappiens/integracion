import frappe
import requests
from frappe import _

def delete_user_in_crm(doc, method):
    # Comprobar si el usuario tiene el rol "Usuario de portal CRM"
    user_roles = [role.role for role in doc.roles]
    if "Usuario de portal CRM" not in user_roles:
        return

    # URL del CRM para eliminar el usuario
    crm_url = f"https://crm.grupoatu.com/api/resource/User/{doc.name}"

    # Encabezados para la solicitud
    headers = {
        "Content-Type": "application/json",
        "Authorization": "token 565da94061d98f1:4182b2cbe6de514"
    }

    # Realizar la solicitud DELETE al CRM para eliminar el usuario
    response = requests.delete(crm_url, headers=headers)

    # Manejar la respuesta del CRM para la eliminación del usuario
    if response.status_code != 200:
        frappe.log_error(message=f"Error al eliminar usuario en CRM: {response.json().get('message')}", title="Eliminar usuario en CRM")
        frappe.throw(f"Error al eliminar usuario en CRM: {response.json().get('message')}")
    else:
        frappe.msgprint(_("Usuario eliminado en CRM"), title="Eliminar usuario en CRM")
        frappe.log_error(message="Usuario eliminado en CRM", title="Eliminar usuario en CRM")