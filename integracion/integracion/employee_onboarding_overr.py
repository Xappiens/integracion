import frappe
from frappe import _
from integracion.integracion.empl_onb_con_over import CustomEmployeeBoardingController




class CustomEmployeeOnboarding(CustomEmployeeBoardingController):
    def validate(self):
        super().validate()
        #self.set_employee()
        #self.validate_duplicate_employee_onboarding()

    def set_employee(self):
        if not self.employee:
            self.employee = frappe.db.get_value("Employee", {"job_applicant": self.job_applicant}, "name")

    def validate_duplicate_employee_onboarding(self):
        # Remover lógica basada en 'job_applicant'
        emp_onboarding = frappe.db.exists(
            "Employee Onboarding", {"employee": self.employee, "docstatus": ("!=", 2)}
        )
        if emp_onboarding and emp_onboarding != self.name:
            frappe.throw(
                _("Employee Onboarding: {0} already exists for Employee: {1}").format(
                    frappe.bold(emp_onboarding), frappe.bold(self.employee)
                )
            )

    def validate_employee_creation(self):
        if self.docstatus != 1:
            frappe.throw(_("Submit this to create the Employee record"))
        else:
            for activity in self.activities:
                if not activity.required_for_employee_creation:
                    continue
                else:
                    task_status = frappe.db.get_value("Task", activity.task, "status")
                    if task_status not in ["Completed", "Cancelled"]:
                        frappe.throw(
                            _("All the mandatory tasks for employee creation are not completed yet."),
                            IncompleteTaskError,
                        )

    def on_submit(self):
        super().on_submit()

    def on_update_after_submit(self):
        self.create_task_and_notify_user()

    def on_cancel(self):
        super().on_cancel()

    @frappe.whitelist()
    def mark_onboarding_as_completed(self):
        for activity in self.activities:
            frappe.db.set_value("Task", activity.task, "status", "Completed")
        frappe.db.set_value("Project", self.project, "status", "Completed")
        self.boarding_status = "Completed"
        self.save()



@frappe.whitelist()
def make_employee(source_name, target_doc=None):
    doc = frappe.get_doc("Employee Onboarding", source_name)
    doc.validate_employee_creation()

    def set_missing_values(source, target):
        # Omite asignaciones basadas en 'job_applicant'
        target.status = "Active"

    doc = get_mapped_doc(
        "Employee Onboarding",
        source_name,
        {
            "Employee Onboarding": {
                "doctype": "Employee",
                "field_map": {
                    "first_name": "employee_name",
                    "employee_grade": "grade",
                },
            }
        },
        target_doc,
        set_missing_values,
    )
    return doc



#def set_job_applicant(doc,method):
#     if not doc.job_applicant:
#         employee = None

#         if doc.custom_empleado:
#             # Obtener el documento del empleado usando el campo custom_empleado
#             employee = frappe.get_doc('Employee', doc.custom_empleado)
#         elif doc.custom_dninie:
#             # Buscar el empleado usando el campo custom_dninie
#             employee_name = frappe.db.get_value('Employee', {'custom_dninie_id': doc.custom_dninie}, 'name')

#             if employee_name:
#                 employee = frappe.get_doc('Employee', employee_name)

#         if employee:
#             # Obtener el email de empleado (empresa, preferido o personal)
#             email_id = employee.company_email or employee.prefered_email or employee.personal_email
#             if not email_id:
#                 # Si el empleado no tiene email, usamos el del solicitante o dirección de contacto
#                 email_id = doc.applicant_email or doc.custom_direccion_de_contacto

#             # Verificar si ya existe un Job Applicant con ese email
#             existing_applicant = frappe.db.get_value('Job Applicant', {'email_id': email_id}, 'name')

#             if existing_applicant:
#                 doc.job_applicant = existing_applicant
#             else:
#                 # Crear un nuevo Job Applicant si no existe
#                 new_job_applicant = frappe.get_doc({
#                     'doctype': 'Job Applicant',
#                     'applicant_name': employee.employee_name,
#                     'email_id': email_id,
#                     'status': 'Open'
#                 })
#                 new_job_applicant.insert(ignore_permissions=True)
#                 doc.job_applicant = new_job_applicant.name

#             doc.applicant_name = employee.employee_name

#             # Actualizar campos del empleado si difieren de los datos de la hoja de contratación
#             if doc.custom_numero_de_movil and doc.custom_numero_de_movil != employee.cell_number:
#                 frappe.db.set_value('Employee', employee.name, 'cell_number', doc.custom_numero_de_movil)

#             if doc.custom_iban and doc.custom_iban != employee.iban:
#                 frappe.db.set_value('Employee', employee.name, 'iban', doc.custom_iban)

#             if doc.custom_no_seguridad_social and doc.custom_no_seguridad_social != employee.custom_no_seguridad_social:
#                 frappe.db.set_value('Employee', employee.name, 'custom_no_seguridad_social', doc.custom_no_seguridad_social)

#             if doc.custom_fecha_de_nacimiento and doc.custom_fecha_de_nacimiento != employee.date_of_birth:
#                 frappe.db.set_value('Employee', employee.name, 'date_of_birth', doc.custom_fecha_de_nacimiento)

#             # Actualizar email preferido
#             preferred_email = doc.applicant_email or doc.custom_direccion_de_contacto
#             if preferred_email and preferred_email != (employee.prefered_email or employee.personal_email):
#                 frappe.db.set_value('Employee', employee.name, 'prefered_email', preferred_email)

#             # Actualizar dirección del empleado si es necesario
#             if doc.custom_direccion and doc.custom_direccion != employee.current_address:
#                 # Concatenar la dirección con el código postal
#                 new_address = f"{doc.custom_direccion}, {doc.custom_codigo_postal}"
#                 frappe.db.set_value('Employee', employee.name, 'current_address', new_address)

