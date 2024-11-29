import frappe
from frappe.model.mapper import get_mapped_doc

@frappe.whitelist()
def make_employee(source_name, target_doc=None):
    def set_missing_values(source, target):
        # Obtener el nombre del Job Applicant
        email_id, full_name = frappe.db.get_value(
            "Job Applicant", source.job_applicant, ["email_id", "applicant_name"]
        )
        
        # Dividir el nombre completo en partes
        name_parts = full_name.split()

        if len(name_parts) == 1:
            # Si solo hay un nombre
            target.first_name = name_parts[0]
            target.middle_name = ''
            target.last_name = ''
        elif len(name_parts) == 2:
            target.first_name = name_parts[0]
            target.middle_name = name_parts[1]
            target.last_name = ''
        elif len(name_parts) == 3:
            target.first_name = name_parts[0]
            target.middle_name = name_parts[1]
            target.last_name = name_parts[2]
        else:
            target.first_name = " ".join(name_parts[:2])
            target.middle_name = name_parts[2]
            target.last_name = " ".join(name_parts[3:])

        # Asignar el correo electrónico
        target.personal_email = email_id

    # Mapeo de Job Offer a Employee
    doc = get_mapped_doc(
        "Job Offer",
        source_name,
        {
            "Job Offer": {
                "doctype": "Employee",
                "field_map": {
                    "applicant_name": "employee_name",  # Mantenemos el employee_name para referencia completa
                    "offer_date": "scheduled_confirmation_date",  # Mapeo existente
                    "custom_fecha_de_nacimiento": "date_of_birth",  # Nuevo mapeo de fecha de nacimiento
                    "custom_fecha_inicio": "date_of_joining",  # Nuevo mapeo de fecha de inicio
                    "custom_fecha_fin": "contract_end_date",  # Nuevo mapeo de fecha de fin de contrato
                    "designation": "designation",  # Mapeo del campo designación
                    "offer_date": "scheduled_confirmation_date",
                    "name": "custom_ultima_hoja"
                },
            }
        },
        target_doc,
        set_missing_values,  # Ejecuta la función que asigna los campos adicionales
    )
    return doc
