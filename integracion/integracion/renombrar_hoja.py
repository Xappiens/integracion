import frappe
from frappe.utils import nowdate
import logging
import os
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Union
from frappe import _
from frappe.model.docstatus import DocStatus
from frappe.utils import cint

if TYPE_CHECKING:
    from frappe.model.document import Document
    from frappe.workflow.doctype.workflow.workflow import Workflow

# Configuración global del log
log_dir = "/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "renombrar_hoja.log")
logging.basicConfig(filename=log_file, level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")



def update_job_offer_states():
    # Guardar el usuario original y cambiar a Administrator
    original_user = frappe.session.user
    frappe.set_user("Administrator")
    logging.info(f"Usuario original: {original_user}")
    logging.info(f"Usuario actual: {frappe.session.user}")
    logging.info("Iniciando el proceso de actualización de estados de Job Offer")

    # Obtener todas las ofertas de trabajo con docstatus = 1 y workflow_state = "Validado"
    job_offers = frappe.get_all("Job Offer", filters={"docstatus": 1, "workflow_state": "Validado"}, fields=["name", "custom_fecha_fin"])
    logging.error(f"Se encontraron {len(job_offers)} ofertas de trabajo con docstatus = 1 y workflow_state = 'Validado'")

    for job in job_offers:
        doc = frappe.get_doc("Job Offer", job.name)
        logging.info(f"Oferta de trabajo encontrada: {doc.name}")

        # Definir la acción basada en custom_fecha_fin
        accion = "Validado a Alta" if str(doc.custom_fecha_fin) >= nowdate() else "Solicitar Baja"

        # Obtener transiciones válidas para verificar si la acción es posible
        from frappe.model.workflow import get_transitions, WorkflowTransitionError
        transiciones = [t.action for t in get_transitions(doc)]

        # Validar si la acción está en las transiciones posibles
        if accion in transiciones:
            try:
                logging.info(f"Aplicando acción '{accion}' a la oferta de trabajo {doc.name}")
                frappe.model.workflow.apply_workflow(doc, accion)
                logging.info(f"Acción '{accion}' aplicada a la oferta de trabajo {doc.name}")

                
                # Log del documento modificado
                logging.info(f"Documento {doc.name} modificado con estado '{accion}'")

            except frappe.PermissionError:
                logging.error(f"Permiso insuficiente para aplicar '{accion}' en {doc.name}")
            except WorkflowTransitionError as e:
                logging.error(f"Error de transición en {doc.name} para '{accion}': {str(e)}")
            except Exception as e:
                # Captura de errores de timestamp y otros errores inesperados
                if "TimestampMismatchError" in str(e):
                    logging.info(f"Documento {doc.name} modificado con estado '{accion}' tras recarga por conflicto de timestamp")
                else:
                    logging.error(f"Error inesperado al guardar {doc.name}: {str(e)}")
        else:
            logging.warning(f"La acción '{accion}' no es válida para el estado actual del documento {doc.name}")

    frappe.set_user(original_user)  # Restaurar el usuario original
    frappe.msgprint("Proceso de actualización de estados de Job Offer completado.")
    logging.info("Proceso de actualización de estados completado.")


@frappe.whitelist()
def change_state_to_baja(doc, action):
    frappe.model.workflow.apply_workflow(doc, action)


def update_job_offer_and_employee(doc, method=None):
    """
    Actualiza campos relacionados con Job Offer y Employee cuando el documento está en estado 'Alta',
    y encola una tarea para aplicar un cambio de estado al Job Offer.
    """
    try:
        if doc.workflow_state == 'Alta' and doc.job_offer:
            hoja = frappe.get_doc('Job Offer', doc.job_offer)
            if hoja.workflow_state == "Baja":
                action = "Restaurar Baja"
                # Encolar la tarea con permisos elevados
                frappe.enqueue(
                    apply_workflow_action,
                    doc_type="Job Offer",
                    doc_name=doc.job_offer,
                    action=action,
                )
                frappe.log_error(f"Tarea encolada para aplicar acción '{action}' al documento {doc.job_offer}")
    except Exception as e:
        frappe.log_error(f"Error al actualizar Job Offer y Employee para el documento {doc.name}: {str(e)}")



def apply_workflow_action(doc_type, doc_name, action):
    """
    Aplica una acción de flujo de trabajo a un documento con permisos elevados.
    """
    try:
        # Cambiar al usuario Administrator
        frappe.set_user("Administrator")
        
        # Obtener el documento y aplicar la acción
        doc = frappe.get_doc(doc_type, doc_name)
        doc.flags.ignore_permissions = True  # Ignorar permisos
        frappe.log_error(f"Aplicando acción '{action}' al documento {doc.name}")
        frappe.model.workflow.apply_workflow(doc, action)
        frappe.log_error(f"Acción '{action}' aplicada correctamente al documento {doc.name}")

    except Exception as e:
        frappe.log_error(f"Error al aplicar acción '{action}' al documento {doc_name}: {str(e)}")
    finally:
        # Restaurar el usuario original para evitar problemas
        frappe.set_user("Administrator")  # Volver al administrador por seguridad
