import frappe
from frappe.utils import nowdate
from datetime import datetime, date, timedelta

from datetime import datetime
from frappe.utils import nowdate

def update_employee_status():
    # Obtener la fecha actual
    today = datetime.strptime(nowdate(), '%Y-%m-%d').date()
    
    # Obtener todos los empleados que no están inactivos
    employees = frappe.get_all('Employee', filters={'status': ['!=', 'Inactive']}, fields=['name', 'status', 'contract_end_date', 'job_applicant'])

    for emp in employees:
        # Si el empleado tiene una fecha de finalización de contrato, usar esa fecha
        if emp.contract_end_date:
            if emp.contract_end_date < today:
                # Cambiar el estado del empleado a 'Inactive' si la fecha de fin ha pasado
                frappe.db.set_value('Employee', emp.name, 'status', 'Inactive')
            elif emp.status != 'Active':
                # Si la fecha de fin no ha pasado, asegurarse de que el estado es 'Active'
                frappe.db.set_value('Employee', emp.name, 'status', 'Active')
        else:
            # Si no hay `contract_end_date`, seguir la lógica basada en Job Offer
            job_offers = frappe.get_all(
                'Job Offer', 
                filters={'custom_empleado': emp.name}, 
                fields=['name', 'custom_fecha_inicio', 'custom_fecha_fin'], 
                order_by='custom_fecha_inicio desc', 
                limit=1
            )
            
            if not job_offers and emp.job_applicant:
                # Si no hay ofertas de trabajo asociadas por custom_empleado, intentar buscar por job_applicant
                job_offers = frappe.get_all(
                    'Job Offer', 
                    filters={'job_applicant': emp.job_applicant}, 
                    fields=['name', 'custom_fecha_inicio', 'custom_fecha_fin'], 
                    order_by='custom_fecha_inicio desc', 
                    limit=1
                )
            
            if job_offers:
                job_offer = job_offers[0]
                # Si la oferta tiene fecha de fin, verificar si ya ha pasado
                if job_offer.custom_fecha_fin:
                    if job_offer.custom_fecha_fin < today:
                        # Cambiar el estado del empleado a 'Inactive' si la fecha de fin ha pasado
                        frappe.db.set_value('Employee', emp.name, 'status', 'Inactive')
                    elif emp.status != 'Active':
                        # Si no ha pasado, asegurarse de que el estado es 'Active'
                        frappe.db.set_value('Employee', emp.name, 'status', 'Active')
                else:
                    # Si no hay fecha de fin, asegurar que el estado es 'Active'
                    if emp.status != 'Active':
                        frappe.db.set_value('Employee', emp.name, 'status', 'Active')

    # Guardar los cambios en la base de datos
    frappe.db.commit()


def disable_inactive_employee_users():
    # Obtener todos los empleados inactivos con un ID de usuario asociado
    inactive_employees = frappe.get_all('Employee', filters={'status': 'Inactive'}, fields=['name', 'user_id'])

    for emp in inactive_employees:
        if emp.user_id:
            # Deshabilitar la cuenta de usuario del empleado
            frappe.db.set_value('User', emp.user_id, 'enabled', 0)

    # Guardar los cambios en la base de datos
    frappe.db.commit()


def check_contract_end():
    # Obtener la fecha actual y la fecha con una semana de anticipación
    today_date = date.today()
    week_from_today = today_date + timedelta(days=7)  # Fecha en 7 días

    # Buscar todos los empleados cuya fecha de fin de contrato sea en 7 días
    employees = frappe.get_all('Employee', filters={'contract_end_date': week_from_today}, fields=['name', 'employee_name', 'job_applicant', 'company'])

    for employee in employees:
        try:
            # Buscar la hoja de contratación (Job Offer) asociada al empleado
            job_offer = frappe.get_all(
                'Job Offer',
                filters={'custom_empleado': employee['name'], 'custom_fecha_fin': week_from_today},
                fields=['name', 'owner'],
                limit=1
            )
            
            # Si no se encuentra por custom_empleado, buscar por job_applicant
            if not job_offer and employee['job_applicant']:
                job_offer = frappe.get_all(
                    'Job Offer',
                    filters={'job_applicant': employee['job_applicant'], 'custom_fecha_fin': week_from_today},
                    fields=['name', 'owner'],
                    limit=1
                )
            
            # Determinar el creador de la hoja de contratación
            job_offer_owner = job_offer[0]['owner'] if job_offer else None

            # Crear el registro de separación de empleado sin la plantilla inicialmente
            employee_separation = frappe.get_doc({
                'doctype': 'Employee Separation',
                'employee': employee['name'],
                'employee_name': employee['employee_name'],
                'company': employee['company'],
                'status': 'Pending',
                'boarding_begins_on': week_from_today,  # Usamos la fecha de separación
                'owner': job_offer_owner  # Asignar al creador de la hoja de contratación
            })
            employee_separation.insert(ignore_permissions=True)
            
            # Asignar la plantilla después de la creación inicial
            employee_separation.employee_separation_template = 'HR-EMP-STP-00001'
            employee_separation.save()  # Guardar para activar las validaciones y agregar las actividades

            # Crear una asignación para la persona que creó la hoja de contratación
            if job_offer_owner:
                todo = frappe.get_doc({
                    'doctype': 'ToDo',
                    'owner': job_offer_owner,
                    'assigned_by': job_offer_owner,
                    'allocated_to': job_offer_owner,
                    'reference_type': 'Employee Separation',
                    'reference_name': employee_separation.name,
                    'description': f"Por favor, gestionar la desincorporación del empleado {employee['employee_name']}."
                })
                todo.insert(ignore_permissions=True)
            
            # Guardar los cambios después de asignar la plantilla
            frappe.db.commit()

        except Exception as e:
            # Registrar cualquier error que ocurra durante el proceso
            frappe.log_error(f"Error al crear la separación para el empleado {employee['name']}: {str(e)[:50]}")
