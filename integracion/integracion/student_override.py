import frappe
import requests
from frappe import _
from education.education.doctype.student.student import Student

class CustomStudent(Student):
    def create_customer(self):
        # Verifica si ya existe un cliente con el nombre del estudiante o el DNI (tax_id)
        customer_name = frappe.db.get_value("Customer", {"customer_name": self.student_name}, "name")
        customer_dni = frappe.db.get_value("Customer", {"tax_id": self.dni}, "name")
        
        # Si el cliente ya existe por nombre o DNI, usa ese cliente
        if customer_name or customer_dni:
            existing_customer = customer_name or customer_dni
            frappe.db.set_value("Student", self.name, "customer", existing_customer)
            
            # Mensaje informando que se vinculó el estudiante al cliente existente
            frappe.msgprint(
                _("Student linked to existing Customer {0}").format(existing_customer),
                alert=True
            )
        else:
            # Si no existe el cliente, créalo
            customer = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": self.student_name,
                "customer_group": self.customer_group or frappe.db.get_single_value("Selling Settings", "customer_group"),
                "customer_type": "Individual",
                "image": self.image,
                # Campos adicionales personalizados
                "custom_tipo_de_identificacion": "DNI",  # Ejemplo de campo adicional predeterminado
                "tax_id": self.dni,  # Relacionar el tax_id del estudiante
                "email_id": self.student_email_id,  # Relacionar el email del estudiante
                "mobile_no": self.student_mobile_number if hasattr(self, 'student_mobile_number') else None,  # Si tienes el campo mobile_no
                # Agregar más campos aquí si es necesario
            }).insert()

            # Vincula el cliente recién creado al estudiante
            frappe.db.set_value("Student", self.name, "customer", customer.name)

            # Mensaje de éxito
            frappe.msgprint(
                _("Customer {0} created and linked to Student").format(customer.name),
                alert=True
            )

    def set_missing_customer_details(self):
        """Sobreescribimos para usar nuestro método create_customer"""
        self.set_customer_group()
        if self.customer:
            self.update_linked_customer()
        else:
            # Usamos el método `create_customer` que hemos sobreescrito
            self.create_customer()


def get_program_enrollment(
    academic_year,
    academic_term=None,
    program=None,
    batch=None,
    student_category=None,
    course=None,
):
    condition1 = " "
    condition2 = " "
    if academic_term:
        condition1 += " and pe.academic_term = %(academic_term)s"
    if program:
        condition1 += " and pe.program = %(program)s"
    if batch:
        condition1 += " and pe.student_batch_name = %(batch)s"
    if student_category:
        condition1 += " and pe.student_category = %(student_category)s"
    if course:
        condition1 += " and pe.name = pec.parent and pec.course = %(course)s"
        condition2 = ", `tabProgram Enrollment Course` pec"

    return frappe.db.sql(
        """
        select
            pe.student, pe.student_name
        from
            `tabProgram Enrollment` pe {condition2}
        where
            pe.academic_year = %(academic_year)s
            and pe.docstatus = 1 {condition1}
        order by
            pe.student_name asc
        """.format(
            condition1=condition1, condition2=condition2
        ),
        (
            {
                "academic_year": academic_year,
                "academic_term": academic_term,
                "program": program,
                "batch": batch,
                "student_category": student_category,
                "course": course,
            }
        ),
        as_dict=1,
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def fetch_students(doctype, txt, searchfield, start, page_len, filters):
    if filters.get("group_based_on") != "Activity":
        enrolled_students = get_program_enrollment(
            filters.get("academic_year"),
            filters.get("academic_term"),
            filters.get("program"),
            filters.get("batch"),
            filters.get("student_category"),
        )
        student_group_student = frappe.db.sql_list(
            """select student from `tabStudent Group Student` where parent=%s""",
            (filters.get("student_group")),
        )

        students = (
            [d.student for d in enrolled_students if d.student not in student_group_student]
            if enrolled_students
            else [""]
        ) or [""]
        return frappe.db.sql(
            """select name, student_name from tabStudent
            where name in ({0}) and (`{1}` LIKE %s or student_name LIKE %s)
            order by idx desc, name
            limit %s, %s""".format(
                ", ".join(["%s"] * len(students)), searchfield
            ),
            tuple(students + ["%%%s%%" % txt, "%%%s%%" % txt, start, page_len]),
        )
    else:
        return frappe.db.sql(
            """select name, student_name from tabStudent
            where `{0}` LIKE %s or student_name LIKE %s
            order by idx desc, name
            limit %s, %s""".format(
                searchfield
            ),
            tuple(["%%%s%%" % txt, "%%%s%%" % txt, start, page_len]),
        )