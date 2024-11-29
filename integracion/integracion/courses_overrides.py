# my_custom_app/custom/course_overrides.py

import frappe
import json
from frappe import _
import requests

def send_course_to_crm(doc, method):
    # Datos del nuevo curso (valores locales)
    course_name_local = doc.course_name  # Campo en el DocType local
    local_name = doc.name  # El nombre del documento que estás insertando

    # URL del CRM remoto
    crm_url = "https://crm.grupoatu.com/api/resource/Course"

    # Encabezados para la solicitud
    headers = {
        "Content-Type": "application/json",
        "Authorization": "token f9e5b8daebc542f:09918536453036a"
    }

    # Datos que enviaremos al CRM remoto
    data = {
        "course_name": course_name_local,  # Nombre del curso del servidor local
        "id_curso": local_name  # Nombre del documento local
    }

    # Realizamos la solicitud POST para crear el curso en el CRM remoto
    try:
        response = requests.post(crm_url, json=data, headers=headers)

        # Verificar el estado de la solicitud
        if response.status_code == 200 or response.status_code == 201:
            pass  # NADA: Todo salió bien
        else:
            frappe.throw(f"Error al crear el curso en el CRM: {response.text}")
    except Exception as e:
        frappe.throw(f"Excepción al conectarse al CRM: {str(e)}")


@frappe.whitelist()
def custom_add_course_to_programs(course, programs, mandatory=False):
    programs = json.loads(programs)
    for entry in programs:
        program = frappe.get_doc("Program", entry)
        # Verifica si el curso ya está en el programa
        if not any(c.course == course for c in program.courses):
            program.append(
                "courses", {"course": course, "course_name": frappe.get_value("Course", course, "course_name"), "mandatory": mandatory}
            )
        program.flags.ignore_mandatory = True
        program.save()
    frappe.msgprint(
        _("Course {0} has been added to all the selected programs successfully.").format(
            frappe.bold(course)
        ),
        title=_("Programs updated"),
        indicator="green",
    )

@frappe.whitelist()
def custom_get_programs_without_course(course):
    data = []
    for entry in frappe.db.get_all("Program"):
        program = frappe.get_doc("Program", entry.name)
        courses = [c.course for c in program.courses]
        if course not in courses:
            data.append(program.name)
    return data


def delete_course_link(doc, method):
    # Obtener todos los programas que tienen vinculado el curso
    programs_with_course = frappe.get_all("Program Course Link", filters={
        "course": doc.name
    }, fields=["parent"])

    # Eliminar el vínculo del curso de cada programa encontrado
    for entry in programs_with_course:
        try:
            # Obtener el documento del programa
            program = frappe.get_doc("Program", entry.parent)

            # Buscar y eliminar el curso en la lista de "courses" del programa
            program.courses = [c for c in program.courses if c.course != doc.name]
            program.save()

        except Exception as e:
            # Registrar el error en los logs
            frappe.log_error(f"Error removing course {doc.name} from program {entry.parent}: {str(e)}")
            # Lanzar una excepción para detener la eliminación
            frappe.throw(f"No se pudo eliminar el curso del programa {entry.parent}. Error: {str(e)}")
