import frappe
from frappe.utils import nowdate
from datetime import datetime

def update_employee_status():
    today = datetime.strptime(nowdate(), '%Y-%m-%d').date()
    employees = frappe.get_all('Employee', filters={'status': ['!=', 'Inactive']}, fields=['name'])

    for emp in employees:
        job_offers = frappe.get_all(
            'Job Offer', 
            filters={'custom_empleado': emp.name}, 
            fields=['name', 'custom_fecha_inicio', 'custom_fecha_fin'], 
            order_by='custom_fecha_inicio desc', 
            limit=1
        )
        
        if job_offers:
            job_offer = job_offers[0]
            if job_offer.custom_fecha_fin:
                if job_offer.custom_fecha_fin < today:
                    frappe.db.set_value('Employee', emp.name, 'status', 'Inactive')
                elif emp.status != 'Active':
                    frappe.db.set_value('Employee', emp.name, 'status', 'Active')
            else:
                if emp.status != 'Active':
                    frappe.db.set_value('Employee', emp.name, 'status', 'Active')

    frappe.db.commit()


def disable_inactive_employee_users():
    inactive_employees = frappe.get_all('Employee', filters={'status': 'Inactive'}, fields=['name', 'user_id'])

    for emp in inactive_employees:
        if emp.user_id:
            frappe.db.set_value('User', emp.user_id, 'enabled', 0)

    frappe.db.commit()
