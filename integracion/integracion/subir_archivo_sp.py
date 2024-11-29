import os
import json
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import quote, urlsplit, urlunsplit, urlencode, parse_qs
from office365.runtime.auth.user_credential import UserCredential
from office365.runtime.auth.client_credential import ClientCredential
from office365.sharepoint.client_context import ClientContext
import frappe
from dataclasses import dataclass
import requests
import re
import inspect
from frappe import _

# Leer credenciales desde el archivo de configuración del sitio
site_config = frappe.get_site_config()
user_email = site_config.get('user_sp')
user_password = site_config.get('pass_sp')
id_cliente = site_config.get('id_sp_client')
secret_sp = site_config.get('secret_sp')
tenant_id = site_config.get('tenant_sp')
auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
cert_pass = site_config.get('cert_key')
cert_path = site_config.get('cert_path')
cert_finger = site_config.get('cert_finger')  # Huella digital del certificado


# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/sharepoint_subida.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)
# Crear un RotatingFileHandler
handler = RotatingFileHandler(
    '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/sharepoint_subida.log',
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3  # Mantener hasta 3 archivos de log antiguos
)

# Mapeo de doctype a estructura de carpetas
folder_structure_map = {
    "Purchase Invoice": ["company", "name"],
    "Sales Invoice": ["company", "customer", "name"],
    "Company": ["name"],
    "Job Offer": ["applicant_name - custom_dninie", "name"],
    "Program": ["name"],
    "Project": ["name"],
    "Room": ["custom_modalidad", "name"],
    "Modificaciones RRHH": ["applicant_name - dni" ,"job_offer","Anexos","name"],
    # Añade aquí más doctypes y su estructura de carpetas 
}



def connect_to_sharepoint_with_token(site_url):
    try:
        # Usar el certificado y la huella digital para autenticarse directamente
        logger.info(f"Conectando al contexto del sitio: {site_url} con huella digital: {cert_finger} y ruta de certificado: {cert_path}")

        # Configurar el contexto de cliente con el certificado
        ctx = ClientContext(site_url).with_client_certificate(
            client_id=id_cliente,
            thumbprint=cert_finger.replace(":", "").upper(),
            cert_path=cert_path,
            tenant=tenant_id
        )
        
        # Probar la conexión accediendo a algún recurso básico
        web = ctx.web.get().execute_query()
        logger.info(f"Conexión exitosa al sitio SharePoint: {web.properties['Title']}")
        
        return ctx
    except Exception as e:
        logger.error(f"Error al conectar a SharePoint con certificado: {e}")
        return None

def sanitize_name(name):
    """
    Reemplaza caracteres prohibidos en SharePoint con un guion, 
    elimina dobles espacios, y quita espacios al inicio o final.
    """
    # Reemplaza caracteres prohibidos
    sanitized_name = name.translate(str.maketrans({
        '*': '-', '"': '-', ':': '-', '<': '-', '>': '-', '?': '-', '/': '-', '\\': '-', '|': '-', ',': '-', '.': '-'
    }))
    
    # Reemplaza dobles o más espacios por uno solo
    sanitized_name = re.sub(r'\s+', ' ', sanitized_name)

    # Elimina espacios al inicio y al final
    sanitized_name = sanitized_name.strip()

    return sanitized_name

def sanitize_url(url):
    """
    Sanitiza la URL codificando los caracteres especiales, incluidos en el path, query y fragment.
    """
    split_url = urlsplit(url)
    sanitized_path = quote(split_url.path, safe='/')
    sanitized_query = urlencode({k: quote(v[0], safe='') for k, v in parse_qs(split_url.query).items()})
    sanitized_fragment = quote(split_url.fragment, safe='')

    return urlunsplit((split_url.scheme, split_url.netloc, sanitized_path, sanitized_query, sanitized_fragment))

def get_folder_structure(doctype, docname, foldername):
    """
    Devuelve la estructura de carpetas para un documento dado.
    """
    if doctype not in folder_structure_map:
        logger.error(f"No se encontró estructura de carpetas para el doctype {doctype}")
        return []

    fields = folder_structure_map[doctype]
    try:
        document = frappe.get_doc(doctype, docname)
        structure = []
        for field in fields:
            if ' - ' in field:
                parts = field.split(' - ')
                combined_field_value = ' - '.join(sanitize_name(document.get(part)) for part in parts if document.get(part))
                if combined_field_value:
                    structure.append(combined_field_value)
            elif field == "name":
                structure.append(sanitize_name(foldername))  # Usa el docname directamente
            elif document.get(field):
                structure.append(sanitize_name(document.get(field)))
            else:
                structure.append(sanitize_name(field))
        
        logger.info(f"Estructura de carpetas para {doctype} {docname}: {structure}")
        return structure
    except Exception as e:
        logger.error(f"Error al obtener la estructura de carpetas para {doctype} {docname}: {e}")
        return []
    


def create_folder_if_not_exists(ctx, folder_relative_url, folder_name):
    try:
        logger.info(f"ctx.web: {dir(ctx.web)}")

        logger.info(f"Comprobando existencia de carpeta en la ruta: {folder_relative_url}/{folder_name}")
        folder_relative_url = folder_relative_url.replace("%20", " ")
        parent_folder = ctx.web.get_folder_by_server_relative_url(f"{folder_relative_url}")
        ctx.load(parent_folder)
        ctx.execute_query()

        folders = parent_folder.folders
        ctx.load(folders)
        ctx.execute_query()

        folder_names = [folder.properties['Name'] for folder in folders]

        if folder_name in folder_names:
            logger.info(f"La carpeta ya existe: {folder_relative_url}/{folder_name}")
        else:
            new_folder = parent_folder.folders.add(folder_name).execute_query()
            logger.info(f"Carpeta creada: {new_folder.serverRelativeUrl}")
    except Exception as e:
        logger.error(f"Error verificando/creando carpeta en {folder_relative_url}/{folder_name}: {e}")
        raise


def handle_structure_change(doc, method):
    try:
        doctype = doc.doctype
        docname = doc.name

        logger.info(f"Verificando cambios estructurales en el documento {doctype} - {docname}")
        
        if doctype not in folder_structure_map:
            logger.info(f"No hay estructura definida para el doctype {doctype}, omitiendo.")
            return
        
        fields_to_check = folder_structure_map[doctype]
        
        # Compara los valores antiguos y los nuevos usando la base de datos directamente
        changes_detected = False
        old_values = {}
        new_values = {}
        
        for field in fields_to_check:
            if field == "name":
                continue  # El nombre del documento no debería cambiar, omítelo
            
            # Obtener tanto el valor antiguo como el nuevo valor desde la base de datos directamente
            old_value = frappe.db.get_value(doctype, docname, field)
            new_value = doc.get(field)  # Valor del objeto actual antes de guardar

            logger.info(f"Comprobando el campo {field}. Valor anterior: {old_value}, Valor nuevo: {new_value}")
            
            if old_value != new_value:
                logger.info(f"Cambio detectado en el campo {field}: de {old_value} a {new_value}.")
                old_values[field] = old_value
                new_values[field] = new_value
                changes_detected = True
        
        if changes_detected:
            logger.info(f"Se han detectado cambios en los valores clave. Iniciando proceso de mover carpetas.")
            
            # Obtener la estructura de carpetas antigua
            old_folder_structure = get_old_folder_structure(doctype, docname, old_values.get('name', docname))
            
            # Obtener la estructura de carpetas nueva basada en los valores "nuevos"
            new_folder_structure = get_new_folder_structure(doctype, new_values, docname)

            if not old_folder_structure or not new_folder_structure:
                logger.error(f"Error al construir la estructura de carpetas. Estructura antigua: {old_folder_structure}, Estructura nueva: {new_folder_structure}")
                return

            logger.info(f"Estructura de carpetas anterior: {old_folder_structure}")
            logger.info(f"Estructura de carpetas nueva: {new_folder_structure}")
            
            # Obtener la URL de SharePoint del documento
            parent_folder_full_url = None
            biblioteca_name = frappe.db.get_value('Bibliotecas SP Docnames', {'docname': docname}, 'parent')

            if biblioteca_name:
                parent_folder_full_url = frappe.db.get_value('Bibliotecas SP', biblioteca_name, 'url_sp')
                logger.info(f"URL encontrada en la tabla hija para {doctype} con docname {docname}: {parent_folder_full_url}")
            else:
                biblioteca_name = frappe.db.get_value('Bibliotecas SP', {'documento': doctype}, 'name')
                if not biblioteca_name:
                    logger.info(f"No se encontró ningún documento en 'Bibliotecas SP' para {doctype}.")
                    return
                
                doc_biblioteca = frappe.get_doc('Bibliotecas SP', biblioteca_name)

                if doc_biblioteca.docnames:
                    matching_entry = next((entry for entry in doc_biblioteca.docnames if entry.docname == docname), None)
                    if matching_entry:
                        parent_folder_full_url = doc_biblioteca.url_sp
                    else:
                        logger.info(f"No se encontró una coincidencia en la tabla hija para {docname}, cancelando la ejecución.")
                        return
                else:
                    parent_folder_full_url = doc_biblioteca.url_sp
                    logger.info(f"Usando la URL general para {doctype}: {parent_folder_full_url}")
            
            # Verificar que se obtuvo la URL correcta
            if not parent_folder_full_url:
                logger.error("No se pudo obtener la URL de la carpeta en SharePoint.")
                return

            # Obtener la ruta relativa en SharePoint
            start_idx = parent_folder_full_url.find('/sites/')
            if start_idx == -1:
                logger.error("La URL no contiene '/sites/'. No se puede calcular la ruta relativa.")
                return
            
            site_url = parent_folder_full_url[:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
            site_relative_path = parent_folder_full_url[start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/') + 1:]
            logger.info(f"Ruta relativa calculada: {site_relative_path}")
            logger.info(f"Conectando al contexto del sitio: {site_url}")

            # Conectar a SharePoint
            ctx = connect_to_sharepoint_with_token(site_url)

            # Asegúrate de que las carpetas en la nueva ruta existan, como en el método `upload_file_to_sharepoint`
            current_relative_path = site_relative_path.strip('/')
            for folder_name in new_folder_structure[:-1]:
                folder_name_sanitized = sanitize_name(folder_name)
                logger.info(f"Verificando existencia o creando carpeta: {current_relative_path}/{folder_name_sanitized}")
                create_folder_if_not_exists(ctx, current_relative_path, folder_name_sanitized)
                current_relative_path = f"{current_relative_path}/{folder_name_sanitized}".strip('/')

            # Ahora que las carpetas padre están creadas o verificadas, movemos la carpeta final
            old_relative_path = f"{site_relative_path}/{'/'.join([sanitize_name(f) for f in old_folder_structure])}"
            new_relative_path = f"{current_relative_path}/{sanitize_name(new_folder_structure[-1])}"

            logger.info(f"Moviendo carpeta {old_relative_path} a {new_relative_path}")

            try:
                destination_parent_path = "/".join(new_relative_path.split('/')[:-1])
                old_folder = ctx.web.get_folder_by_server_relative_url(old_relative_path)
                old_folder.move_to(destination_parent_path).execute_query()
                logger.info(f"Carpeta movida exitosamente de {old_relative_path} a {destination_parent_path}")
            except Exception as e:
                logger.error(f"Error al mover la carpeta de {old_relative_path} a {new_relative_path}: {e}")
        else:
            logger.info(f"No se detectaron cambios en los valores clave, no se requiere mover carpetas.")
    except Exception as e:
        logger.error(f"Error en handle_structure_change para {docname}: {e}")

# Método para obtener la estructura antigua
def get_old_folder_structure(doctype, docname, foldername):
    """
    Devuelve la estructura de carpetas basada en los valores antiguos de la base de datos.
    """
    if doctype not in folder_structure_map:
        logger.error(f"No se encontró estructura de carpetas para el doctype {doctype}")
        return []

    fields = folder_structure_map[doctype]
    try:
        structure = []
        for field in fields:
            if ' - ' in field:
                parts = field.split(' - ')
                combined_field_value = ' - '.join(sanitize_name(frappe.db.get_value(doctype, docname, part)) for part in parts if frappe.db.get_value(doctype, docname, part))
                if combined_field_value:
                    structure.append(combined_field_value)
            elif field == "name":
                structure.append(sanitize_name(foldername))  # Usa el docname directamente
            else:
                value = frappe.db.get_value(doctype, docname, field)
                if value:
                    structure.append(sanitize_name(value))
        
        logger.info(f"Estructura de carpetas antigua para {doctype} {docname}: {structure}")
        return structure
    except Exception as e:
        logger.error(f"Error al obtener la estructura de carpetas antigua para {doctype} {docname}: {e}")
        return []

# Método para obtener la estructura nueva basada en los valores nuevos detectados
def get_new_folder_structure(doctype, new_values, foldername):
    """
    Devuelve la estructura de carpetas basada en los valores nuevos detectados.
    """
    if doctype not in folder_structure_map:
        logger.error(f"No se encontró estructura de carpetas para el doctype {doctype}")
        return []

    fields = folder_structure_map[doctype]
    try:
        structure = []
        for field in fields:
            if ' - ' in field:
                parts = field.split(' - ')
                combined_field_value = ' - '.join(sanitize_name(new_values.get(part)) for part in parts if new_values.get(part))
                if combined_field_value:
                    structure.append(combined_field_value)
            elif field == "name":
                structure.append(sanitize_name(foldername))  # Usa el docname directamente
            else:
                value = new_values.get(field)
                if value:
                    structure.append(sanitize_name(value))
        
        logger.info(f"Estructura de carpetas nueva para {doctype}: {structure}")
        return structure
    except Exception as e:
        logger.error(f"Error al obtener la estructura de carpetas nueva para {doctype}: {e}")
        return []

def upload_file_to_sharepoint(doc, method):
    logger.info(f"Hook llamado al subir File: {doc.name}")
    try:
        file_doc = frappe.get_doc('File', doc.name)
        file_path = frappe.get_site_path(file_doc.file_url.strip("/"))
        logger.info(f"Archivo encontrado: {file_path}")

        if not file_path or not os.path.isfile(file_path):
            logger.error(f"El archivo no existe o no se proporcionó una ruta válida: {file_path}")
            return

        doctype_name = file_doc.attached_to_doctype
        docname = file_doc.attached_to_name
        foldername = sanitize_name(docname)
        project_type = None

        if doctype_name == "Job Offer":
            job_offer_doc = frappe.get_doc('Job Offer', docname)
            if job_offer_doc.status != "Accepted":
                logger.info(f"El estado de la oferta de trabajo no es 'Accepted', no se subirá el archivo.")
                return

        if doctype_name == "Project":
            project_doc = frappe.get_doc('Project', docname)
            if project_doc.project_type:
                project_type = project_doc.project_type
            else:
                logger.info(f"El proyecto no tiene Project type seleccionado")
                return

        # Primera Verificación: Consultar directamente en la tabla hija si existe un registro con docname igual a doc.name
        parent_folder_full_url = None
        if project_type:
            biblioteca_name = frappe.db.get_value(
                'Bibliotecas SP Docnames',
                {'docname': project_type},
                'parent'
            )
            logger.info(f"Tabla hija: {biblioteca_name}")
        else:
            biblioteca_name = frappe.db.get_value(
                'Bibliotecas SP Docnames', 
                {'docname': docname}, 
                'parent'
            )
            logger.info(f"Tabla hija: {biblioteca_name}")

        if biblioteca_name:
            # Si existe, obtener la URL del registro padre
            parent_folder_full_url = frappe.db.get_value('Bibliotecas SP', biblioteca_name, 'url_sp')
            logger.info(f"URL encontrada en la tabla hija para {doctype_name} con docname {docname}: {parent_folder_full_url}")
        else:
            # Segunda Verificación: Buscar en 'Bibliotecas SP' por doctype_name
            biblioteca_name = frappe.db.get_value('Bibliotecas SP', {'documento': doctype_name}, 'name')
            if not biblioteca_name:
                logger.info(f"No se encontró ningún documento en 'Bibliotecas SP' para {doctype_name}.")
                return
            
            doc_biblioteca = frappe.get_doc('Bibliotecas SP', biblioteca_name)

            if doc_biblioteca.docnames:
                # Si la tabla hija no está vacía, pero no se encontró coincidencia en la búsqueda anterior
                logger.info(f"Tabla hija no vacía, verificando si {docname} está en la tabla hija.")
                matching_entry = next((entry for entry in doc_biblioteca.docnames if entry.docname == docname), None)
                if matching_entry:
                    parent_folder_full_url = doc_biblioteca.url_sp
                else:
                    logger.info(f"No se encontró una coincidencia en la tabla hija para {docname}, cancelando la ejecución.")
                    return
            else:
                # Si la tabla hija está vacía, usamos la URL general
                parent_folder_full_url = doc_biblioteca.url_sp
                logger.info(f"Tabla hija vacía, usando la URL general para {doctype_name}: {parent_folder_full_url}")

        # Continuar con la lógica de conexión a SharePoint y subida de archivo
        start_idx = parent_folder_full_url.find('/sites/')
        if start_idx == -1:
            logger.error("La URL no contiene '/sites/'. No se puede calcular la ruta relativa.")
            return
        
        site_url = parent_folder_full_url[:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
        site_relative_path = parent_folder_full_url[start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/') + 1:]
        logger.info(f"Ruta relativa calculada: {site_relative_path}")
        logger.info(f"Conectando al contexto del sitio: {site_url}")

        ctx = connect_to_sharepoint_with_token(site_url)

        folder_structure = get_folder_structure(doctype_name, docname, foldername)
        if not folder_structure:
            logger.error(f"No se encontró la estructura de carpetas para {doctype_name} con nombre {docname}")
            return

        current_relative_path = site_relative_path.strip('/')
        for folder_name in folder_structure:
            folder_name_sanitized = sanitize_name(folder_name)
            folder_name_encoded = quote(folder_name_sanitized)
            create_folder_if_not_exists(ctx, current_relative_path, folder_name_encoded)
            current_relative_path = f"{current_relative_path}/{folder_name_encoded}".strip('/')

        with open(file_path, 'rb') as file_content:
            content = file_content.read()

        file_name = os.path.basename(file_path)
        file_url = f"{current_relative_path}/{file_name}"
        logger.info(f"Intentando subir archivo a: {file_url}")

        try:
            target_folder = ctx.web.get_folder_by_server_relative_url(current_relative_path)
            ctx.load(target_folder)
            ctx.execute_query()

            target_folder.upload_file(file_name, content).execute_query()
            logger.info(f"Archivo subido: {file_url}")
            
            frappe.delete_doc('File', doc.name, force=True)
            logger.info(f"Archivo {file_name} eliminado de ERPNext")
        except Exception as e:
            logger.error(f"Error al subir archivo a SharePoint: {str(e)}")
    except Exception as e:
        logger.error(f"Error al subir archivo a SharePoint: {str(e)}")


def on_update_or_create(doc, method):
    upload_file_to_sharepoint(doc, method)


@frappe.whitelist(allow_guest=True)
def get_sharepoint_structure(doctype, docname):
    foldername = sanitize_name(docname)
    lista = []
    project_type = None
    
    # Verificación específica para "Project"
    if doctype == "Project":
        project_doc = frappe.get_doc('Project', docname)
        if project_doc.project_type:
            project_type = project_doc.project_type
        else:
            logger.info(f"El proyecto no tiene Project type seleccionado")
            return

    # Primera Verificación: Consultar directamente en la tabla hija si existe un registro con docname igual a docname
    parent_folder_full_url = None
    if project_type:
        biblioteca_name = frappe.db.get_value(
            'Bibliotecas SP Docnames',
            {'docname': project_type},
            'parent'
        )
        logger.info(f"Tabla hija: {biblioteca_name}")
    else:
        biblioteca_name = frappe.db.get_value(
            'Bibliotecas SP Docnames', 
            {'docname': docname}, 
            'parent'
        )
        logger.info(f"Tabla hija: {biblioteca_name}")

    if biblioteca_name:
        # Si existe, obtener la URL del registro padre
        parent_folder_full_url = frappe.db.get_value('Bibliotecas SP', biblioteca_name, 'url_sp')
        logger.info(f"URL encontrada en la tabla hija para {doctype} con docname {docname}: {parent_folder_full_url}")
    else:
        # Segunda Verificación: Buscar en 'Bibliotecas SP' por doctype_name
        try:
            biblioteca_name = frappe.db.get_value('Bibliotecas SP', {'documento': doctype}, 'name')

            if not biblioteca_name:
                logger.info(f"No se encontró ningún documento en 'Bibliotecas SP' con documento {doctype}.")
                return json.dumps([])

            doc_biblioteca = frappe.get_doc('Bibliotecas SP', biblioteca_name)
        except frappe.DoesNotExistError:
            logger.error(f"No se encontró un documento para el doctype {doctype} en Bibliotecas SP. Terminando la ejecución.")
            return json.dumps([])

        if doc_biblioteca.docnames:
            # Si la tabla hija no está vacía, pero no se encontró coincidencia en la búsqueda anterior
            logger.info(f"Tabla hija no vacía, verificando si {docname} está en la tabla hija.")
            matching_entry = next((entry for entry in doc_biblioteca.docnames if entry.docname == docname), None)
            if matching_entry:
                parent_folder_full_url = doc_biblioteca.url_sp
            else:
                logger.info(f"No se encontró una coincidencia en la tabla hija para {docname}, terminando la ejecución.")
                return json.dumps([])
        else:
            # Si la tabla hija está vacía, usamos la URL general
            parent_folder_full_url = doc_biblioteca.url_sp
            logger.info(f"Tabla hija vacía, usando la URL general para {doctype}: {parent_folder_full_url}")

    logger.info(f"URL de la carpeta padre: {parent_folder_full_url}")

    start_idx = parent_folder_full_url.find('/sites/')
    if start_idx == -1:
        logger.error("La URL no contiene '/sites/'. No se puede calcular la ruta relativa.")
        return json.dumps([])
    
    site_url = parent_folder_full_url[:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
    site_relative_path = parent_folder_full_url[start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/') + 1:]
    logger.info(f"Ruta relativa calculada: {site_relative_path}")
    logger.info(f"Conectando al contexto del sitio: {site_url}")

    ctx = connect_to_sharepoint_with_token(site_url)
    folder_check = ctx.web.get_folder_by_server_relative_url


    def carpeta_existe(ctx, folder_relative_url, folder_name, modalidad=None, doctype=None):
        """
        Modificado para buscar carpetas recursivamente y manejar modalidad.
        La modalidad solo se usa si el doctype es "Room".
        """
        try:
            if doctype == "Room":
                if modalidad:
                    logger.info(f"Buscando carpeta por modalidad: {modalidad}")
                    # Si hay modalidad, buscamos la carpeta exacta con ese nombre
                    modalidad_folder_url = f"{folder_relative_url}/{sanitize_name(modalidad)}"
                    modalidad_folder_url = modalidad_folder_url.replace("%20", " ")
                    carpeta = ctx.web.get_folder_by_server_relative_url(modalidad_folder_url)
                    ctx.load(carpeta)
                    ctx.execute_query()
                    logger.info(f"Carpeta modalidad encontrada: {modalidad_folder_url}")
                    return modalidad_folder_url  # Retorna la URL si se encuentra la carpeta
                else:
                    # Si no hay modalidad o no existe, buscamos recursivamente carpetas que comiencen con folder_name
                    logger.info("No hay modalidad, buscando recursivamente en subcarpetas.")
                    return buscar_carpeta_en_subcarpetas(ctx, folder_relative_url, folder_name)
            else:
                try:
                    carpeta_url = f"{folder_relative_url}/{folder_name}"
                    carpeta_url = carpeta_url.replace("%20", " ")
                    logger.info(f"Verificando existencia de carpeta en la ruta: {carpeta_url}")
                    
                    carpeta = ctx.web.get_folder_by_server_relative_url(carpeta_url)
                    logger.info(f"Carpeta: {type(carpeta)}")
                    ctx.load(carpeta)
                    try:
                        logger.debug(f"Contenido de pending_request antes de execute_query: {ctx.pending_request()}")
                        ctx.execute_query()
                    except Exception as e:
                        logger.error(f"Error cargando carpeta: {e}")
                    logger.info(f"Folder loaded: {ctx}")
                    return True
                except Exception as e:
                    logger.error(f"Error verificando existencia de carpeta en {carpeta_url}: {e}")
                    return False

        except Exception as e:
            logger.error(f"Error verificando existencia de carpeta en {folder_relative_url}/{folder_name}: {e}")
            return False

    def buscar_carpeta_en_subcarpetas(ctx, folder_relative_url, folder_name):
        """
        Función recursiva para buscar carpetas en todas las subcarpetas.
        """
        try:
            root_folder = ctx.web.get_folder_by_server_relative_url(folder_relative_url)
            folders = root_folder.folders
            ctx.load(folders)
            ctx.execute_query()

            for folder in folders:
                folder_name_in_sp = folder.properties['Name']
                if folder_name_in_sp.startswith(folder_name):
                    logger.info(f"Se encontró una carpeta que comienza con '{folder_name}': {folder_name_in_sp}")
                    return f"{folder_relative_url}/{folder_name_in_sp}"  # Devuelve la ruta completa

            for folder in folders:
                folder_name_in_sp = folder.properties['Name']
                subfolder_relative_url = f"{folder_relative_url}/{folder_name_in_sp}"
                
                result = buscar_carpeta_en_subcarpetas(ctx, subfolder_relative_url, folder_name)
                if result:
                    return result

            return False

        except Exception as e:
            logger.error(f"Error buscando carpeta en subcarpetas desde {folder_relative_url}: {e}")
            return False

    # Obtener la estructura de carpetas
    folder_structure = get_folder_structure(doctype, docname, foldername)
    if not folder_structure:
        logger.error(f"No se encontró la estructura de carpetas para {doctype} con nombre {docname}")
        return json.dumps([])

    # Aplicar la modalidad solo si el doctype es "Room"
    modalidad = None
    if doctype == "Room":
        modalidad = frappe.db.get_value(doctype, docname, 'custom_modalidad')  
    logger.info(f"MODALIDAD: {modalidad}")
    # Verificar si existe la carpeta final basada en la estructura
    current_relative_path = site_relative_path.strip('/')
    carpeta_actual = None
    for i, folder_name in enumerate(folder_structure):
        folder_name_sanitized = sanitize_name(folder_name)
        folder_name_encoded = quote(folder_name_sanitized)
        next_relative_path = f"{current_relative_path}/{folder_name_encoded}".strip('/')
        logger.info(f"Verificando existencia de carpeta en la ruta: {current_relative_path}/{folder_name_encoded}")
        
        # Usar modalidad si está presente y es el primer nivel de la estructura
        if i == 0 and modalidad:
            modalidad_folder_url = carpeta_existe(ctx, current_relative_path, folder_name_encoded, modalidad,doctype)
            modalidad = None  # Solo se usa la modalidad en el primer nivel
            if modalidad_folder_url:
                current_relative_path = modalidad_folder_url.strip('/')
                logger.info(f"Carpeta modalidad utilizada: {modalidad_folder_url}")
                continue

        if carpeta_existe(ctx, current_relative_path, folder_name_encoded,modalidad,doctype):
            logger.info(f"La carpeta ya existe: {next_relative_path}")
            if i == len(folder_structure) - 1:
                carpeta_raiz = {
                    "tipo": "C",
                    "nombre": folder_name_sanitized,
                    'url': f"{site_url}/{next_relative_path}",
                    "children": []
                }
                lista.append(carpeta_raiz)
                carpeta_actual = carpeta_raiz
        else:
            logger.error(f"No se encontró la carpeta {folder_name} en {current_relative_path}")
            return json.dumps([])

        current_relative_path = next_relative_path

    if carpeta_actual:
        procesa_carpeta(ctx, site_url, current_relative_path, carpeta_actual)

    logger.info(f"Lista: {json.dumps(lista)}")
    return json.dumps(lista)



def procesa_carpeta(ctx, share, ruta, carpeta_actual):
    try:
        logger.info(f"Ruta: {ruta}")
        logger.info(f"Share: {share}")
        root = ctx.web.get_folder_by_server_relative_url(f'{ruta}')
        folders = root.folders
        ctx.load(folders)
        ctx.execute_query()
        logger.info(f"Folders loaded: {folders}")  # Log details of loaded folders
        
        for folder in folders:
            logger.info(f"Processing folder: {folder.properties['Name']}")
            subcarpeta = {
                "tipo": "C",
                "nombre": folder.properties["Name"],
                'url': f"{share}/{ruta}/{folder.properties['Name']}",
                "children": []
            }
            carpeta_actual["children"].append(subcarpeta)
            procesa_carpeta(ctx, share, f"{ruta}/{folder.properties['Name']}", subcarpeta)
        
        files = root.files
        ctx.load(files)
        ctx.execute_query()
        logger.info(f"Files loaded: {files}")  # Log details of loaded files
        
        for file in files:
            carpeta_actual["children"].append({
                "tipo": "F",
                "nombre": file.properties["Name"],
                'url': f"{share}/{ruta}/{file.properties['Name']}"
            })
            logger.info(f"File added to list: {file.properties['Name']}")
        
        logger.info(f"Estructura obtenida: {json.dumps(carpeta_actual)}")
    except Exception as e:
        logger.error(f"Error procesando la carpeta {ruta}: {e}")


def create_project_folder(doc, method):
    """
    Hook para crear la carpeta base automáticamente cuando se inserta un proyecto.
    """
    logger.info(f"Creando carpeta para el proyecto: {doc.name}")
    
    try:
        doctype = "Project"
        docname = doc.name
        foldername = sanitize_name(docname)
        
        # Obtener la URL de SharePoint del documento
        parent_folder_full_url = None
        project_type = None
        
        if doc.project_type:
            project_type = doc.project_type
            biblioteca_name = frappe.db.get_value(
                'Bibliotecas SP Docnames',
                {'docname': project_type},
                'parent'
            )
            logger.info(f"Tabla hija: {biblioteca_name}")
        else:
            biblioteca_name = frappe.db.get_value(
                'Bibliotecas SP Docnames',
                {'docname': docname},
                'parent'
            )
            logger.info(f"Tabla hija: {biblioteca_name}")
        
        if biblioteca_name:
            parent_folder_full_url = frappe.db.get_value('Bibliotecas SP', biblioteca_name, 'url_sp')
            logger.info(f"URL encontrada en la tabla hija para Project con docname {docname}: {parent_folder_full_url}")
        else:
            # Si no se encuentra en la tabla hija, buscar en 'Bibliotecas SP' general
            biblioteca_name = frappe.db.get_value('Bibliotecas SP', {'documento': doctype}, 'name')
            if not biblioteca_name:
                logger.info(f"No se encontró ningún documento en 'Bibliotecas SP' para {doctype}.")
                return

            doc_biblioteca = frappe.get_doc('Bibliotecas SP', biblioteca_name)

            if doc_biblioteca.docnames:
                matching_entry = next((entry for entry in doc_biblioteca.docnames if entry.docname == docname), None)
                if matching_entry:
                    parent_folder_full_url = doc_biblioteca.url_sp
                else:
                    logger.info(f"No se encontró una coincidencia en la tabla hija para {docname}, cancelando la ejecución.")
                    return
            else:
                parent_folder_full_url = doc_biblioteca.url_sp
                logger.info(f"Usando la URL general para {doctype}: {parent_folder_full_url}")

        # Verificar que se obtuvo la URL correcta
        if not parent_folder_full_url:
            logger.error("No se pudo obtener la URL de la carpeta en SharePoint.")
            return

        # Obtener la ruta relativa en SharePoint
        start_idx = parent_folder_full_url.find('/sites/')
        if start_idx == -1:
            logger.error("La URL no contiene '/sites/'. No se puede calcular la ruta relativa.")
            return

        site_url = parent_folder_full_url[:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
        site_relative_path = parent_folder_full_url[start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/') + 1:]
        logger.info(f"Ruta relativa calculada: {site_relative_path}")
        logger.info(f"Conectando al contexto del sitio: {site_url}")

        # Conectar a SharePoint
        ctx = connect_to_sharepoint_with_token(site_url)

        # Obtener la estructura de carpetas del proyecto
        folder_structure = get_folder_structure(doctype, docname, foldername)
        if not folder_structure:
            logger.error(f"No se encontró la estructura de carpetas para {doctype} con nombre {docname}")
            return

        # Crear la estructura de carpetas en SharePoint
        current_relative_path = site_relative_path.strip('/')
        for folder_name in folder_structure:
            folder_name_sanitized = sanitize_name(folder_name)
            logger.info(f"Verificando existencia o creando carpeta: {current_relative_path}/{folder_name_sanitized}")
            create_folder_if_not_exists(ctx, current_relative_path, folder_name_sanitized)
            current_relative_path = f"{current_relative_path}/{folder_name_sanitized}".strip('/')

        logger.info(f"Carpeta creada exitosamente para el proyecto {docname}.")

    except Exception as e:
        logger.error(f"Error al crear la carpeta para el proyecto {docname}: {e}")
