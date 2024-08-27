import os
import json
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import quote, urlsplit, urlunsplit, urlencode, parse_qs
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
import frappe
from frappe import _

# Leer credenciales desde el archivo de configuración del sitio
site_config = frappe.get_site_config()
user_email = site_config.get('user_sp')
user_password = site_config.get('pass_sp')

# Configurar el logger
logger = logging.getLogger(__name__)

# Crear un RotatingFileHandler
# maxBytes es el tamaño máximo del archivo en bytes antes de que se rote
# backupCount es el número de archivos de respaldo que se conservarán
handler = RotatingFileHandler(
    '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/upload_sp.log',
    maxBytes=5 * 1024 * 1024,  # 5 MB
    backupCount=3  # Mantener hasta 3 archivos de log antiguos
)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Mapeo de doctype a estructura de carpetas
folder_structure_map = {
    "Purchase Invoice": ["company", "name"],
    "Sales Invoice": ["company", "customer", "name"],
    "Company": ["name"],
    "Job Offer": ["applicant_name - custom_dninie", "name"],
    "Program": ["name"],
    "Project": ["name"],
    # Añade aquí más doctypes y su estructura de carpetas 
}

def sanitize_name(name):
    """
    Reemplaza caracteres prohibidos en SharePoint con un guion.
    """
    return name.translate(str.maketrans({
        '*': '-', '"': '-', ':': '-', '<': '-', '>': '-', '?': '-', '/': '-', '\\': '-', '|': '-', ',': '-', '.': '-'
    }))

def sanitize_url(url):
    """
    Sanitiza la URL codificando los caracteres especiales, incluidos en el path, query y fragment.
    """
    # Divide la URL en sus componentes
    split_url = urlsplit(url)
    
    # Sanitiza el path, que es la parte que suele tener caracteres especiales
    sanitized_path = quote(split_url.path, safe='/')
    
    # Sanitiza la query si existe
    sanitized_query = urlencode({k: quote(v[0], safe='') for k, v in parse_qs(split_url.query).items()})
    
    # Sanitiza el fragmento si existe
    sanitized_fragment = quote(split_url.fragment, safe='')

    # Vuelve a ensamblar la URL completa con el path, query y fragmento sanitizados
    sanitized_url = urlunsplit((split_url.scheme, split_url.netloc, sanitized_path, sanitized_query, sanitized_fragment))
    
    return sanitized_url

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
        # Crear la estructura utilizando los campos del documento, sanitizando cada nombre
        structure = []
        for field in fields:
            if ' - ' in field:
                # Si el campo es una combinación, dividirlo y combinar los valores
                parts = field.split(' - ')
                combined_field_value = ' - '.join(sanitize_name(document.get(part)) for part in parts if document.get(part))
                if combined_field_value:
                    structure.append(combined_field_value)
            elif field == "name":
                structure.append(sanitize_name(foldername))  # Usa el docname directamente
            elif document.get(field):
                structure.append(sanitize_name(document.get(field)))
        
        logger.info(f"Estructura de carpetas para {doctype} {docname}: {structure}")
        return structure
    except Exception as e:
        logger.error(f"Error al obtener la estructura de carpetas para {doctype} {docname}: {e}")
        return []

def create_folder_if_not_exists(ctx, folder_relative_url, folder_name):
    try:
        logger.info(f"Comprobando existencia de carpeta en la ruta: {folder_relative_url}/{folder_name}")
        logger.info(f"Ruta relativa de carpeta: {folder_relative_url}")
        parent_folder = ctx.web.get_folder_by_server_relative_url(f"{folder_relative_url}")
        ctx.load(parent_folder)
        ctx.execute_query()
        logger.info(f"Conectado a parent {parent_folder}")

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

        credentials = UserCredential(user_email, user_password)
        ctx = ClientContext(site_url).with_credentials(credentials)

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

    credentials = UserCredential(user_email, user_password)
    ctx = ClientContext(site_url).with_credentials(credentials)

    def carpeta_existe(ctx, folder_relative_url, folder_name):
        try:
            folder = ctx.web.get_folder_by_server_relative_url(f"{folder_relative_url}/{folder_name}")
            ctx.load(folder)
            ctx.execute_query()
            return True
        except Exception as e:
            logger.error(f"Error verificando existencia de carpeta en {folder_relative_url}/{folder_name}: {e}")
            return False

    # Obtener la estructura de carpetas
    folder_structure = get_folder_structure(doctype, docname, foldername)
    if not folder_structure:
        logger.error(f"No se encontró la estructura de carpetas para {doctype} con nombre {docname}")
        return json.dumps([])

    # Verificar si existe la carpeta final basada en la estructura
    current_relative_path = site_relative_path.strip('/')
    carpeta_actual = None
    for i, folder_name in enumerate(folder_structure):
        folder_name_sanitized = sanitize_name(folder_name)
        folder_name_encoded = quote(folder_name_sanitized)
        next_relative_path = f"{current_relative_path}/{folder_name_encoded}".strip('/')
        if carpeta_existe(ctx, current_relative_path, folder_name_encoded):
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
