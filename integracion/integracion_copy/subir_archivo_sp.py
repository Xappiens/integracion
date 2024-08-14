import os
import json
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import quote
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
    # Añade aquí más doctypes y su estructura de carpetas deseada
}

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
        # Crear la estructura utilizando los campos del documento
        structure = []
        for field in fields:
            if field == "name":
                structure.append(foldername)  # Usa el docname directamente
            elif document.get(field):
                structure.append(document.get(field))
        
        logger.info(f"Estructura de carpetas para {doctype} {docname}: {structure}")
        return structure
    except Exception as e:
        logger.error(f"Error al obtener la estructura de carpetas para {doctype} {docname}: {e}")
        return []

def create_folder_if_not_exists(ctx, folder_relative_url, folder_name):
    try:
        logger.info(f"Comprobando existencia de carpeta en la ruta: {folder_relative_url}/{folder_name}")
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

def sanitize_name(name):
    """
    Reemplaza caracteres prohibidos en SharePoint con un guion.
    """
    return name.translate(str.maketrans({
        '*': '-', '"': '-', ':': '-', '<': '-', '>': '-', '?': '-', '/': '-', '\\': '-', '|': '-'
    }))


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
        

        doc_biblioteca = frappe.get_doc('Bibliotecas SP', doctype_name)
        if not doc_biblioteca:
            return
        parent_folder_full_url = doc_biblioteca.url_sp
        logger.info(f"URL de la carpeta padre: {parent_folder_full_url}")

        # Extraer la ruta relativa y el nombre del sitio desde la URL completa
        start_idx = parent_folder_full_url.find('/sites/')
        if start_idx == -1:
            logger.error("La URL no contiene '/sites/'. No se puede calcular la ruta relativa.")
            return
        
        site_url = parent_folder_full_url[:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
        # Ajuste aquí para obtener la ruta correcta sin el nombre del sitio
        site_relative_path = parent_folder_full_url[start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/') + 1:]
        logger.info(f"Ruta relativa calculada: {site_relative_path}")
        logger.info(f"Conectando al contexto del sitio: {site_url}")

        credentials = UserCredential(user_email, user_password)
        ctx = ClientContext(site_url).with_credentials(credentials)

        # Obtener la estructura de carpetas
        folder_structure = get_folder_structure(doctype_name, docname, foldername)
        if not folder_structure:
            logger.error(f"No se encontró la estructura de carpetas para {doctype_name} con nombre {docname}")
            return
        
        # Crear carpetas según la estructura
        current_relative_path = site_relative_path.strip('/')
        for folder_name in folder_structure:
            folder_name_encoded = quote(folder_name)
            create_folder_if_not_exists(ctx, current_relative_path, folder_name_encoded)
            current_relative_path = f"{current_relative_path}/{folder_name_encoded}".strip('/')

        # Última carpeta creada es donde se sube el archivo
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
    try:
        doc_biblioteca = frappe.get_doc('Bibliotecas SP', doctype)
    except frappe.DoesNotExistError:
        logger.error(f"No se encontró un documento para el doctype {doctype} en Bibliotecas SP. Terminando la ejecución.")
        return json.dumps([])

    parent_folder_full_url = doc_biblioteca.url_sp
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
        folder_name_encoded = quote(folder_name)
        next_relative_path = f"{current_relative_path}/{folder_name_encoded}".strip('/')
        if carpeta_existe(ctx, current_relative_path, folder_name_encoded):
            logger.info(f"La carpeta ya existe: {next_relative_path}")
            if i == len(folder_structure) - 1:
                carpeta_raiz = {
                    "tipo": "C",
                    "nombre": folder_name,
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

