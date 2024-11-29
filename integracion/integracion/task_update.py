import frappe

def update_activity_state(doc, method):
    # Busca la actividad en el doctype `Employee Boarding Activity` que está vinculada a esta tarea
    activity_records = frappe.get_all(
        "Employee Boarding Activity",
        filters={"task": doc.name},
        fields=["parent"]
    )

    # Itera sobre cada actividad que tiene esta tarea asociada
    for activity in activity_records:
        try:
            # Intenta cargar el documento principal de `Employee Onboarding` usando el campo `parent`
            onboarding_doc = frappe.get_doc("Employee Onboarding", activity['parent'])

            # Verifica si el documento de `Employee Onboarding` no está cancelado
            if onboarding_doc.docstatus != 2:  # 2 significa "Cancelado"
                # Itera sobre las actividades en `Employee Onboarding` para encontrar la fila correspondiente
                for activity_row in onboarding_doc.activities:
                    if activity_row.task == doc.name:
                        # Actualiza el estado en la fila de actividad si no está cancelado
                        activity_row.state = doc.status
                
                # Intenta guardar el documento principal con los cambios
                onboarding_doc.flags.ignore_permissions = True
                onboarding_doc.save(ignore_permissions=True, ignore_version=True)
        
        # Ignora silenciosamente cualquier error si el documento no existe o tiene campos obligatorios faltantes
        except (frappe.DoesNotExistError, frappe.MandatoryError):
            pass
