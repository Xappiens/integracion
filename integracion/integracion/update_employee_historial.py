import frappe
from frappe.utils import today  # Importar today para resolver el primer error
from frappe.model.workflow import apply_workflow  # Importar apply_workflow
import json

def update_employee_historial():
    # Obtener todos los empleados activos de la tabla Employee
    employees = frappe.get_all(
        'Employee', 
        filters={'status': 'Active'},  # Filtrar solo empleados activos
        fields=['name', 'employee_name', 'custom_dninie_id']
    )

    for emp in employees:
        try:
            # Obtener el valor del DNI/NIE y el nombre completo en mayúsculas
            dni_nie = emp.custom_dninie_id or emp.name
            full_name = (emp.employee_name or '').upper() if emp.employee_name else emp.name
            
            # Verificar que DNI/NIE esté disponible
            if not dni_nie:
                print(f"⚠️  DNI/NIE no disponible para el empleado {full_name}. Saltando este empleado.")
                continue

            # Obtener todas las Job Offers aceptadas que coinciden con el DNI/NIE del empleado
            job_offers = frappe.get_all(
                'Job Offer',
                filters={
                    'workflow_state': ['in', ['Alta', 'Baja']],  # Incluir tanto "Alta" como "Baja"
                    'docstatus': 1,
                    'custom_dninie': dni_nie
                },
                fields=['name', 'custom_fecha_inicio', 'custom_fecha_fin', 'custom_tipo_de_contrato', 'designation', 'company', 'workflow_state', 'custom_solicitud_baja'],
                order_by='custom_fecha_inicio desc'
            )

            # Obtener todas las modificaciones en Modificaciones RRHH que coinciden con el DNI/NIE del empleado
            anexos = frappe.get_all(
                'Modificaciones RRHH',
                filters={
                    'workflow_state': 'Alta',
                    'docstatus': 1,
                    'custom_dninie': dni_nie
                },
                fields=['name', 'start_date', 'designation', 'workflow_state']
            )

            # Cargar el documento del empleado
            empleado_doc = frappe.get_doc('Employee', emp.name)

            # Verificar si la tabla hija custom_historial_altas existe
            if not hasattr(empleado_doc, 'custom_historial_altas'):
                print(f"⚠️  El empleado {full_name} no tiene el campo 'custom_historial_altas'. Saltando este empleado.")
                continue

            # Variable para rastrear si se hicieron cambios
            updated = False

            # Crear entradas para Job Offers
            for job_offer in job_offers:
                # Determinar la fecha en función del estado del flujo de trabajo
                fecha = job_offer['custom_solicitud_baja'] if job_offer['workflow_state'] == 'Baja' else job_offer['custom_fecha_inicio']
                
                # Asegurar que la fecha existe antes de agregarla
                if not fecha:
                    print(f"⚠️  No se encontró una fecha válida para la Job Offer '{job_offer['name']}' del empleado {full_name}. Saltando esta oferta.")
                    continue

                # Crear instancia de la tabla hija
                historial_entry = {
                    'documento': 'Job Offer',
                    'hoja_anexo': job_offer['name'],
                    'accion': job_offer['workflow_state'],
                    'fecha': fecha,
                    'puesto': job_offer['designation']
                }
                empleado_doc.append('custom_historial_altas', historial_entry)
                updated = True
                print(f"✅ Entrada añadida a custom_historial_altas para Job Offer '{job_offer['name']}' del empleado {full_name}")

            # Crear entradas para Modificaciones RRHH
            for anexo in anexos:
                # Verificar si los datos esenciales existen antes de añadir
                if not anexo.get('start_date') or not anexo.get('designation'):
                    print(f"⚠️  Datos incompletos para el anexo '{anexo['name']}' del empleado {full_name}. Saltando este anexo.")
                    continue

                # Crear instancia de la tabla hija
                historial_entry = {
                    'documento': 'Modificaciones RRHH',
                    'hoja_anexo': anexo['name'],
                    'accion': anexo['workflow_state'],
                    'fecha': anexo['start_date'],
                    'puesto': anexo['designation']
                }
                empleado_doc.append('custom_historial_altas', historial_entry)
                updated = True
                print(f"✅ Entrada añadida a custom_historial_altas para Modificaciones RRHH '{anexo['name']}' del empleado {full_name}")

            # Guardar los cambios en el registro del empleado si hubo actualizaciones
            if updated:
                empleado_doc.save(ignore_permissions=True)
                frappe.db.commit()
                print(f"✅ Historial actualizado para el empleado: {full_name}")
            else:
                print(f"ℹ️  No se realizaron cambios para el empleado: {full_name}")

        except Exception as e:
            print(f"❌ Error al actualizar el historial para el empleado {emp.name}: {str(e)}")

@frappe.whitelist()
def update_job_offer_states():
    # Obtener todas las ofertas de trabajo con docstatus = 1
    job_offers = frappe.get_all("Job Offer", filters={"docstatus": 1}, fields=["name", "custom_fecha_fin"])

    for job in job_offers:
        doc = frappe.get_doc("Job Offer", job.name)

        # Verificar si custom_fecha_fin tiene un valor antes de compararlo
        if doc.custom_fecha_fin:
            if doc.custom_fecha_fin >= today():
                # Cambiar el estado a "Alta"
                try:
                    apply_workflow(frappe.as_json(doc), "Validado a Alta")
                except frappe.PermissionError:
                    frappe.log_error(f"No se pudo aplicar 'Validado a Alta' en {doc.name} debido a permisos insuficientes.")
            else:
                # Cambiar el estado a "Baja"
                try:
                    apply_workflow(frappe.as_json(doc), "Validado a Baja")
                except frappe.PermissionError:
                    frappe.log_error(f"No se pudo aplicar 'Validado a Baja' en {doc.name} debido a permisos insuficientes.")

            # Guardar el documento con el nuevo estado
            doc.save()
        else:
            frappe.log_error(f"El documento {doc.name} no tiene custom_fecha_fin asignado.")

    frappe.msgprint("Estados de las ofertas de trabajo actualizados según 'custom_fecha_fin'.")

from datetime import date, datetime

def date_handler(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f'Object of type {type(obj)} is not JSON serializable')

def insert_historial_altas(doc, method=None):
    try:
        dni_nie = doc.custom_dninie_id or doc.name

        # Obtener Job Offers
        job_offers = frappe.get_all(
            'Job Offer',
            filters={
                'workflow_state': ['in', ['Alta', 'Baja']],
                'docstatus': 1,
                'custom_dninie': dni_nie
            },
            fields=['name', 'custom_fecha_inicio', 'custom_solicitud_baja', 'designation', 'workflow_state'],
            order_by='custom_fecha_inicio desc'
        )

        # En lugar de usar json.dumps para el log, usamos una representación más simple
        frappe.log_error(f"Número de Job Offers encontradas: {len(job_offers)}")

        # Insertar Job Offers
        for job_offer in job_offers:
            fecha = job_offer.custom_solicitud_baja if job_offer.workflow_state == 'Baja' else job_offer.custom_fecha_inicio
            idx = frappe.db.sql("""
                SELECT IFNULL(MAX(idx), 0) + 1 
                FROM `tabEmpleado Historial Altas` 
                WHERE parent = %s
            """, doc.name)[0][0]

            frappe.db.sql("""
                INSERT INTO `tabEmpleado Historial Altas` 
                (name, parent, parenttype, parentfield, documento, hoja_anexo, 
                 accion, fecha, puesto, idx, owner, creation, modified, modified_by)
                VALUES (%s, %s, 'Employee', 'custom_historial_altas', %s, %s, 
                        %s, %s, %s, %s, %s, NOW(), NOW(), %s)
            """, (
                frappe.generate_hash(),
                doc.name,
                'Job Offer',
                job_offer.name,
                job_offer.workflow_state,
                fecha,
                job_offer.designation,
                idx,
                frappe.session.user,
                frappe.session.user
            ))

        # Obtener Anexos
        anexos = frappe.get_all(
            'Modificaciones RRHH',
            filters={
                'workflow_state': 'Alta',
                'docstatus': 1,
                'custom_dninie': dni_nie
            },
            fields=['name', 'start_date', 'designation', 'workflow_state']
        )

        frappe.log_error(f"Número de Anexos encontrados: {len(anexos)}")

        # Insertar Anexos
        for anexo in anexos:
            idx = frappe.db.sql("""
                SELECT IFNULL(MAX(idx), 0) + 1 
                FROM `tabEmpleado Historial Altas` 
                WHERE parent = %s
            """, doc.name)[0][0]

            frappe.db.sql("""
                INSERT INTO `tabEmpleado Historial Altas` 
                (name, parent, parenttype, parentfield, documento, hoja_anexo, 
                 accion, fecha, puesto, idx, owner, creation, modified, modified_by)
                VALUES (%s, %s, 'Employee', 'custom_historial_altas', %s, %s, 
                        %s, %s, %s, %s, %s, NOW(), NOW(), %s)
            """, (
                frappe.generate_hash(),
                doc.name,
                'Modificaciones RRHH',
                anexo.name,
                anexo.workflow_state,
                anexo.start_date,
                anexo.designation,
                idx,
                frappe.session.user,
                frappe.session.user
            ))

        frappe.db.commit()
        frappe.clear_cache(doctype="Employee", name=doc.name)
        frappe.log_error("Proceso completado exitosamente")

    except Exception as e:
        frappe.log_error(f"Error al insertar historial de altas: {str(e)}")