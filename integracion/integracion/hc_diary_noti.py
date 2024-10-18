import frappe

def enviar_notificacion_a_asesoria():
    # Obtener las hojas de contratación validadas hoy
    hojas_contratacion = frappe.get_all('Job Offer', 
        filters={'custom_fecha_validacion': frappe.utils.now()},
        fields=['name', 'applicant_name'])

    # Verificar si hay hojas de contratación
    if not hojas_contratacion:
        frappe.log_error("No hay hojas de contratación validadas hoy.")
        return
    
    # Log para verificar las hojas de contratación
    frappe.log_error(f'Hojas de contratación: {len(hojas_contratacion)}')
    
    # Inicializar la lista HTML para el cuerpo del correo
    contenido_html = """
    <h3>Hojas de Contratación Validadas Hoy:</h3>
    <ul>
    """
    
    # Crear una lista HTML con cada hoja de contratación
    for hoja in hojas_contratacion:
        hoja_name = hoja.get('name', 'Nombre no disponible')
        applicant = hoja.get('applicant_name', 'Solicitante no disponible')

        # Crear el enlace para cada hoja de contratación y añadirlo a la lista
        contenido_html += f"""
        <li>
            <a href="https://erp.grupoatu.com/app/job-offer/{hoja_name}" target="_blank">
                {hoja_name} - {applicant}
            </a>
        </li>
        """
    
    # Cerrar la lista HTML
    contenido_html += "</ul>"

    # Obtener los correos electrónicos de los usuarios con el rol 'Asesoría'
    usuarios_asesoria = frappe.get_all('Has Role', 
        filters={'role': 'Asesoría'}, 
        fields=['parent'])

    correos = []
    for usuario in usuarios_asesoria:
        user_email = frappe.db.get_value('User', usuario['parent'], 'email')
        if user_email:
            correos.append(user_email)

    if not correos:
        frappe.log_error("No se encontraron usuarios con el rol 'Asesoría'.")
        return

    # Enviar el correo con cola de correos habilitada
    try:
        frappe.sendmail(
            recipients=correos,
            subject="Hojas de Contratación Validadas Hoy",
            message=contenido_html,
            delayed=False   # Enviar a través de la cola de correos
        )
        frappe.log_error(f"Notificación enviada correctamente a: {', '.join(correos)}")
    except Exception as e:
        frappe.log_error(f"Error al enviar la notificación: {str(e)}")
