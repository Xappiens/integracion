import frappe

def job_offer_query(user):
    # Verificar si el usuario tiene el rol "Asesoría" directamente en la base de datos
    has_asesoria_role = frappe.db.exists('Has Role', {'parent': user, 'role': 'Asesoría'})
    
    # Si el usuario tiene el rol "Asesoría", aplicar el filtro
    if has_asesoria_role:
        return "`tabJob Offer`.docstatus >= 0"

    return ""

def user_query(user):
    # Verificar si el usuario tiene el Role Profile 'Base'
    role_profile = frappe.db.get_value('User', user, 'role_profile_name')

    if role_profile == 'Base':
        # Si el usuario tiene el Role Profile 'Base', limitar la vista a su propio usuario
        return f"`tabUser`.`name` = '{user}'"
    else:
        # Si no tiene el Role Profile 'Base', excluir a 'Guest' y 'Administrator'
        return "`tabUser`.`name` NOT IN ('Guest', 'Administrator')"

def attendance_query(user):
    # Verificar si el usuario tiene el Role Profile 'Base'
    user_roles = frappe.get_roles(user)
    if 'HR Manager' in user_roles:
        return ""
    else:
        employee = frappe.get_value('Employee', {'user_id': user}, 'name')
        return f"`tabAttendance`.employee = '{employee}'"

def project_query(user):
    # Obtener los roles del usuario
    user_roles = frappe.get_roles(user)

    if 'Projects Manager' in user_roles:
        return ""
    
    # Obtener los tipos de proyecto que tengan alguno de esos roles
    project_types_with_roles = frappe.get_all('Rol Tipo Proyecto', 
        filters={'rol': ['in', user_roles]}, 
        fields=['parent']
    )
    
    # Extraer los nombres de los tipos de proyecto
    project_type_names = [p['parent'] for p in project_types_with_roles]

    # Si hay tipos de proyecto que coinciden con los roles del usuario, aplicamos el filtro
    if project_type_names:
        project_type_filter = ', '.join([f"'{ptype}'" for ptype in project_type_names])
        return f"`tabProject`.project_type IN ({project_type_filter})"
    
    # Si no hay coincidencias, no mostramos proyectos
    return "1 = 0"


def course_query(user):
    # Verificar el Role Profile del usuario
    role_profile = frappe.db.get_value('User', user, 'role_profile_name')

    if role_profile == 'Instructor':
        # Obtener el ID del Instructor usando el correo del usuario conectado
        instructor = frappe.db.get_value('Instructor', {'mail': user}, 'name')
        
        if instructor:
            # Consultar los Course asociados al Instructor en la tabla 'Instructor Curso'
            course_list = frappe.get_all('Instructor Curso', 
                                         filters={'instructor': instructor}, 
                                         fields=['parent'])
            
            # Extraer los IDs de los Course asociados
            course_ids = [course['parent'] for course in course_list]
            
            if course_ids:
                # Limitar la vista a los cursos asociados al instructor encontrado
                course_ids_str = ', '.join([f"'{course_id}'" for course_id in course_ids])
                return f"`tabCourse`.`name` IN ({course_ids_str})"
            else:
                # Si no hay cursos asociados, evitar mostrar resultados
                return "1 = 0"
    
    elif user == 'Administrator':
        # Si el usuario es 'Administrator', permitir ver todos los cursos
        return "1 = 1"
    
    # Para otros usuarios, evitar mostrar cursos
    return "1 = 0"
