import frappe
from frappe import _
from frappe.desk.form import assign_to
from frappe.model.document import Document
from frappe.utils import add_days, flt, unique

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

class CustomEmployeeBoardingController(Document):
    """
    Custom implementation of EmployeeBoardingController.
    """
    
    def validate(self):
        # Eliminar la tarea si está vinculada antes de enviar el formulario
        if self.amended_from:
            for activity in self.activities:
                activity.task = ""

    def on_submit(self):
        # Crear el proyecto basado solo en 'employee', eliminando 'job_applicant'
        project_name = _(self.doctype) + " : "
        if self.doctype == "Employee Onboarding":
            project_name += self.employee
        elif self.doctype == "Employee Separation":
            project_name += self.employee_name
        else:
            project_name += self.employee
        project_without_date = project_name
        project_name += " - " + self.date_of_joining
                    # Tipo de proyecto según el tipo de documento
        if self.doctype == "Employee Separation":
            project_type = "Separacion Empleado"
        elif self.doctype == "Employee Onboarding":
            project_type = "Onboarding Empleado"
        else:
            project_type = None  # Puedes ajustar este valor según tu lógica
        if frappe.db.exists("Project", {"project_name": project_name}):
            project_name = project_without_date + " - " + self.creation

        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": project_name,
            "project_type": project_type,
            "expected_start_date": self.date_of_joining
                if self.doctype == "Employee Onboarding"
                else self.resignation_letter_date,
            "department": self.department,
            "company": self.company,
        }).insert(ignore_permissions=True, ignore_mandatory=True)

        # Establecer los valores del proyecto en el documento
        self.db_set("project", project.name)
        self.db_set("boarding_status", "Pending")
        self.reload()

        # Llamar al método que crea tareas y notifica a los usuarios
        self.create_task_and_notify_user()



    def create_task_and_notify_user(self):
        # Obtener la lista de días festivos
        holiday_list = self.get_holiday_list()

        for activity in self.activities:
            if activity.task:
                continue

            # Obtener fechas para la tarea
            dates = self.get_task_dates(activity, holiday_list)

            # Crear la tarea
            task = frappe.get_doc({
                "doctype": "Task",
                "project": self.project,
                "subject": activity.activity_name + " : " + self.employee_name,
                "description": activity.description,
                "department": self.department,
                "company": self.company,
                "task_weight": activity.task_weight,
                "exp_start_date": dates[0],
                "exp_end_date": dates[1],
            }).insert(ignore_permissions=True)


            # Asignamos la tarea al registro de actividad
            activity.db_set("task", task.name)

            # Obtener usuarios del equipo HD
            users = []
            if activity.hd_team:
                team_members = frappe.get_all("HD Team Member", filters={"parent": activity.hd_team}, fields=["user"])
                users = [member.user for member in team_members]

            # Obtener usuarios con el rol asignado
            if activity.role:
                user_list = frappe.db.sql_list("""
                    SELECT DISTINCT(has_role.parent)
                    FROM `tabHas Role` has_role
                    LEFT JOIN `tabUser` user ON has_role.parent = user.name
                    WHERE has_role.parenttype = 'User'
                        AND user.enabled = 1
                        AND has_role.role = %s
                """, activity.role)

                # Añadir usuarios de rol a la lista de usuarios y eliminar duplicados
                users = unique(users + user_list)

            # Eliminar "Administrator" de la lista de usuarios
            if "Administrator" in users:
                users.remove("Administrator")

            # Asignar la tarea a los usuarios si hay alguno
            if users:
                self.assign_task_to_users(task, users)

    def assign_task_to_users(self, task, users):
        """Asigna la tarea a los usuarios de HD Team y por rol."""

        # Importamos el método correcto para asignar tareas
        from frappe.desk.form.assign_to import add

        for user in users:
            args = {
                "assign_to": [user],
                "doctype": task.doctype,
                "name": task.name,
                "description": task.description or task.subject,
                "notify": self.notify_users_by_email,  # Notificar a los usuarios por correo
            }
            
            # Aquí utilizamos el método 'add' que maneja la asignación de tareas
            add(args)

    def get_holiday_list(self):
        if self.employee:
            return get_holiday_list_for_employee(self.employee)
        else:
            if not self.holiday_list:
                frappe.throw(_("Please set the Holiday List."), frappe.MandatoryError)
            else:
                return self.holiday_list

    def get_task_dates(self, activity, holiday_list):
        start_date = end_date = None

        if activity.begin_on is not None:
            start_date = add_days(self.boarding_begins_on, activity.begin_on)
            start_date = self.update_if_holiday(start_date, holiday_list)

            if activity.duration is not None:
                end_date = add_days(self.boarding_begins_on, activity.begin_on + activity.duration)
                end_date = self.update_if_holiday(end_date, holiday_list)

        return [start_date, end_date]

    def update_if_holiday(self, date, holiday_list):
        while is_holiday(holiday_list, date):
            date = add_days(date, 1)
        return date

    def on_cancel(self):
        # Eliminar proyecto y tareas vinculadas
        project = self.project
        for task in frappe.get_all("Task", filters={"project": project}):
            frappe.delete_doc("Task", task.name, force=1)
        frappe.delete_doc("Project", project, force=1)
        self.db_set("project", "")
        for activity in self.activities:
            activity.db_set("task", "")

        frappe.msgprint(
            _("Linked Project {} and Tasks deleted.").format(project), alert=True, indicator="blue"
        )
