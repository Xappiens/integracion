# /your_custom_app/overrides/program_enrollment.py
import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Min
from frappe.utils import comma_and, getdate
from frappe import _, msgprint
from frappe.desk.reportview import get_match_cond
from education.education.doctype.fee_schedule.fee_schedule import (
    create_sales_invoice,
    create_sales_order,
)
from frappe.email.doctype.email_group.email_group import add_subscribers
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cstr, flt, getdate
from frappe.utils.dateutils import get_dates_from_timegrain

class CustomProgramEnrollment(Document):
    def validate(self):
        self.set_student_name()
        self.validate_duplication()

        # Si no hay cursos asignados, obtén cursos predeterminados y añádelos
        if not self.courses:
            self.extend("courses", self.get_courses())

    def set_student_name(self):
        if not self.student_name:
            # Obtener el nombre del estudiante en base al ID del estudiante
            self.student_name = frappe.db.get_value("Student", self.student, "student_name")

    def on_submit(self):
        # Actualiza la fecha de ingreso del estudiante
        self.update_student_joining_date()
        # Crea los registros de tasas correspondientes
        self.make_fee_records()
        # Crea las inscripciones de los cursos
        self.create_course_enrollments()

    def on_cancel(self):
        # Eliminar inscripciones a los cursos al cancelar
        self.delete_course_enrollments()

    def validate_duplication(self):
        # Verifica que no haya duplicados de inscripción para el mismo estudiante, programa, etc.
        enrollment = frappe.db.exists(
            "Program Enrollment",
            {
                "student": self.student,
                "program": self.program,
                "academic_year": self.academic_year,
                "academic_term": self.academic_term,
                "docstatus": ("<", 2),
                "name": ("!=", self.name),
            },
        )
        if enrollment:
            frappe.throw(_("Student is already enrolled in this program."))

    def update_student_joining_date(self):
        # Actualiza la fecha de ingreso del estudiante con base en la inscripción más antigua
        table = frappe.qb.DocType("Program Enrollment")
        date = (
            frappe.qb.from_(table)
            .select(Min(table.enrollment_date).as_("enrollment_date"))
            .where(table.student == self.student)
        ).run(as_dict=True)

        if date:
            frappe.db.set_value("Student", self.student, "joining_date", date[0].enrollment_date)

    def make_fee_records(self):
        # Genera los registros de tasas (facturas o órdenes de venta) según la configuración
        create_so = frappe.db.get_single_value("Education Settings", "create_so")

        fees_list = []
        doctype = ""
        for d in self.fees:
            if create_so:
                sales_order = create_sales_order(d.fee_schedule, self.student)
                doctype = "Sales Order"
                fees_list.append(sales_order)
            else:
                sales_invoice = create_sales_invoice(d.fee_schedule, self.student)
                doctype = "Sales Invoice"
                fees_list.append(sales_invoice)

        if fees_list:
            fees_list = [
                """<a href="/app/Form/%s/%s" target="_blank">%s</a>""" % (doctype, fee, fee)
                for fee in fees_list
            ]
            msgprint(_("Fee Records Created - {0}").format(comma_and(fees_list)))

    @frappe.whitelist()
    def get_courses(self):
        # Obtiene los cursos asociados al programa actual
        return frappe.db.sql(
            """select course from `tabProgram Course Link` where parent = %s""",
            (self.program),
            as_dict=1,
        )

    def create_course_enrollments(self):
        # Crear inscripciones a los cursos para el estudiante si no existen
        for course in self.courses:
            filters = {
                "student": self.student,
                "course": course.course,
                "program_enrollment": self.name,
            }
            if not frappe.db.exists("Course Enrollment", filters):
                filters.update(
                    {"doctype": "Course Enrollment", "enrollment_date": self.enrollment_date}
                )
                frappe.get_doc(filters).save()

    def get_all_course_enrollments(self):
        # Obtiene todas las inscripciones a los cursos asociados a esta inscripción en el programa
        course_enrollment_names = frappe.get_list(
            "Course Enrollment", filters={"program_enrollment": self.name}
        )
        return [
            frappe.get_doc("Course Enrollment", course_enrollment.name)
            for course_enrollment in course_enrollment_names
        ]

    def delete_course_enrollments(self):
        # Elimina las inscripciones a los cursos asociadas a esta inscripción
        for course_enrollment in self.get_all_course_enrollments():
            frappe.delete_doc("Course Enrollment", course_enrollment.name)


# # Métodos adicionales, por ejemplo para obtener los cursos o estudiantes

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_program_courses(doctype, txt, searchfield, start, page_len, filters):
    if not filters.get("program"):
        frappe.msgprint(_("Please select a Program first."))
        return []

    doctype = "Program Course Link"
    return frappe.db.sql(
        """select course, course_name from `tabProgram Course Link`
        where  parent = %(program)s and course like %(txt)s {match_cond}
        order by
            if(locate(%(_txt)s, course), locate(%(_txt)s, course), 99999),
            idx desc,
            `tabProgram Course Link`.course asc
        limit {start}, {page_len}""".format(
            match_cond=get_match_cond(doctype), start=start, page_len=page_len
        ),
        {
            "txt": "%{0}%".format(txt),
            "_txt": txt.replace("%", ""),
            "program": filters["program"],
        },
    )

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_students(doctype, txt, searchfield, start, page_len, filters):
    # Si no se pasa academic_term o academic_year, obtenemos los valores por defecto
    if not filters.get("academic_term"):
        filters["academic_term"] = frappe.defaults.get_defaults().academic_term

    if not filters.get("academic_year"):
        filters["academic_year"] = frappe.defaults.get_defaults().academic_year

    # Aquí simplemente obtenemos los estudiantes, sin filtrar por inscripción previa
    return frappe.db.sql(
        """select
            name, student_name 
        from 
            tabStudent
        where
            `{0}` LIKE %s or student_name LIKE %s
        order by
            idx desc, name
        limit %s, %s""".format(searchfield),
        tuple(["%%%s%%" % txt, "%%%s%%" % txt, start, page_len])
    )



@frappe.whitelist()
def custom_enroll_student(source_name):
    """Creates a Student Record and returns a Program Enrollment.
    
    :param source_name: Student Applicant.
    """
    
    # Publicar el progreso de la inscripción
    frappe.publish_realtime(
        "enroll_student_progress", {"progress": [1, 4]}, user=frappe.session.user
    )
    
    # Obtener el documento mapeado de Student Applicant a Student
    student = get_mapped_doc(
        "Student Applicant",
        source_name,
        {
            "Student Applicant": {
                "doctype": "Student",
                "field_map": {
                    "name": "student_applicant",
                },
            }
        },
        ignore_permissions=True,
    )
    student.save()

    # Obtener información del Student Applicant
    student_applicant = frappe.db.get_value(
        "Student Applicant",
        source_name,
        ["student_category", "program", "academic_year", "course"],  # Agregamos el campo 'course'
        as_dict=True,
    )

    # Crear un nuevo Program Enrollment
    program_enrollment = frappe.new_doc("Program Enrollment")
    program_enrollment.student = student.name
    program_enrollment.student_category = student_applicant.student_category
    program_enrollment.student_name = student.student_name
    program_enrollment.program = student_applicant.program
    program_enrollment.academic_year = student_applicant.academic_year
    
    # Añadir el curso seleccionado a la tabla de courses en Program Enrollment
    if student_applicant.course:  # Si hay un curso seleccionado en Student Applicant
        program_enrollment.append("courses", {
            "course": student_applicant.course  # Añadimos el curso
        })

    # Guardar el documento de Program Enrollment
    program_enrollment.save()

    # Publicar el progreso actualizado
    frappe.publish_realtime(
        "enroll_student_progress", {"progress": [2, 4]}, user=frappe.session.user
    )

    return program_enrollment

