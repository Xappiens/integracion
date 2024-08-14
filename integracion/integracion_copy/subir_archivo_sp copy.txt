import os
import json
import logging
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
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/upload_sp.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def get_parent_folder_name(doctype, docname):
    fields_to_check = ['company', 'empresa', 'custom_empresa']
    logger.info(f"Obteniendo campos del documento {doctype} con nombre {docname}")
    try:
        related_doc = frappe.get_doc(doctype, docname)
        logger.info(f"Campos del documento {doctype}: {related_doc.as_dict()}")
        for field in fields_to_check:
            if field in related_doc.as_dict():
                logger.info(f"Campo {field} encontrado con valor {related_doc.get(field)}")
                return related_doc.get(field)
    except Exception as e:
        logger.error(f"Error obteniendo el documento {doctype} con nombre {docname}: {e}")
        return None

def create_folder_if_not_exists(ctx, folder_relative_url, folder_name):
    try:
        logger.info(f"Comprobando existencia de carpeta en la ruta: /{folder_relative_url}/{folder_name}")
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
        site_relative_url = parent_folder_full_url[start_idx:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
        relative_path = parent_folder_full_url[start_idx + len(site_relative_url):].lstrip('/')
        logger.info(f"Ruta relativa calculada: {relative_path}")
        logger.info(f"Conectando al contexto del sitio: {site_url}")

        credentials = UserCredential(user_email, user_password)
        ctx = ClientContext(site_url).with_credentials(credentials)

        parent_folder_name = get_parent_folder_name(doctype_name, docname)
        if not parent_folder_name:
            logger.error(f"No se encontró el nombre de la carpeta padre para {doctype_name} con nombre {docname}")
            return
        parent_folder_name_encoded = quote(parent_folder_name)
        logger.info(f"Nombre de la carpeta padre: {parent_folder_name}")

        # Crear la primera carpeta
        create_folder_if_not_exists(ctx, relative_path, parent_folder_name_encoded)

        # Crear la carpeta secundaria
        second_folder_relative_url = f"{relative_path}/{parent_folder_name_encoded}".strip('/')
        create_folder_if_not_exists(ctx, second_folder_relative_url, docname)

        with open(file_path, 'rb') as file_content:
            content = file_content.read()

        file_name = os.path.basename(file_path)
        file_url = f"{second_folder_relative_url}/{docname}/{file_name}"
        logger.info(f"Intentando subir archivo a: {file_url}")

        try:
            target_folder = ctx.web.get_folder_by_server_relative_url(f"{second_folder_relative_url}/{docname}")
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
    site_relative_url = parent_folder_full_url[start_idx:]
    relative_path = parent_folder_full_url[start_idx + len('/sites/'):].lstrip('/')
    logger.info(f"Ruta relativa calculada: {relative_path}")
    logger.info(f"Conectando al contexto del sitio: {site_url}")

    credentials = UserCredential(user_email, user_password)
    ctx = ClientContext(site_url).with_credentials(credentials)

    def carpeta_existe(ctx, folder_relative_url, folder_name):
        try:
            folder = ctx.web.get_folder_by_server_relative_url(f"/{folder_relative_url}/{folder_name}")
            ctx.load(folder)
            ctx.execute_query()
            return True
        except Exception as e:
            logger.error(f"Error verificando existencia de carpeta en {folder_relative_url}/{folder_name}: {e}")
            return False

    # Verificar si existe la carpeta directamente en la raíz con el docname
    root_folder_url = f"{relative_path}/{docname}".strip('/')
    if carpeta_existe(ctx, relative_path, docname):
        logger.info(f"La carpeta raíz ya existe: {root_folder_url}")
        carpeta_raiz = {
            "tipo": "C",
            "nombre": docname,
            'url': f"{site_url}/{root_folder_url}",
            "children": []
        }
        lista.append(carpeta_raiz)
        procesa_carpeta(ctx, site_url, root_folder_url, carpeta_raiz)
    else:
        logger.info(f"La carpeta raíz no existe, procediendo a verificar carpetas secundarias.")

        parent_folder_name = get_parent_folder_name(doctype, docname)
        if not parent_folder_name:
            logger.error(f"No se encontró el nombre de la carpeta padre para {doctype} con nombre {docname}")
            return json.dumps([])

        parent_folder_name_encoded = quote(parent_folder_name)
        first_folder_relative_url = f"{relative_path}/{parent_folder_name_encoded}".strip('/')
        second_folder_relative_url = f"{first_folder_relative_url}/{docname}".strip('/')
        logger.info(f"URL de la primera carpeta: {first_folder_relative_url}")
        logger.info(f"URL completa de la carpeta del documento: {second_folder_relative_url}")

        if carpeta_existe(ctx, first_folder_relative_url, docname):
            carpeta_raiz = {
                "tipo": "C",
                "nombre": docname,
                'url': f"{site_url}/{second_folder_relative_url}",
                "children": []
            }
            lista.append(carpeta_raiz)
            procesa_carpeta(ctx, site_url, second_folder_relative_url, carpeta_raiz)
        else:
            logger.error(f"No se encontró la carpeta secundaria para {docname} en {first_folder_relative_url}")

    logger.info(f"Lista: {json.dumps(lista)}")
    return json.dumps(lista)

@frappe.whitelist(allow_guest=True)
def get_sharepoint_structure(doctype, docname):
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
    
    # Construir la URL del sitio y la parte relativa
    site_url = parent_folder_full_url[:start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/')]
    site_relative_url = parent_folder_full_url[start_idx:]
    relative_path = parent_folder_full_url[start_idx + len('/sites/') + parent_folder_full_url[start_idx + len('/sites/'):].find('/') + 1:].lstrip('/')
    logger.info(f"Ruta relativa calculada: {relative_path}")
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

    # Verificar si existe la carpeta directamente en la raíz con el docname
    root_folder_url = f"{relative_path}/{docname}".strip('/')
    if carpeta_existe(ctx, relative_path, docname):
        logger.info(f"La carpeta raíz ya existe: {root_folder_url}")
        carpeta_raiz = {
            "tipo": "C",
            "nombre": docname,
            'url': f"{site_url}/{root_folder_url}",
            "children": []
        }
        lista.append(carpeta_raiz)
        procesa_carpeta(ctx, site_url, root_folder_url, carpeta_raiz)
    else:
        logger.info(f"La carpeta raíz no existe, procediendo a verificar carpetas secundarias.")

        parent_folder_name = get_parent_folder_name(doctype, docname)
        if not parent_folder_name:
            logger.error(f"No se encontró el nombre de la carpeta padre para {doctype} con nombre {docname}")
            return json.dumps([])

        parent_folder_name_encoded = quote(parent_folder_name)
        first_folder_relative_url = f"{relative_path}/{parent_folder_name_encoded}".strip('/')
        second_folder_relative_url = f"{first_folder_relative_url}/{docname}".strip('/')
        logger.info(f"URL de la primera carpeta: {first_folder_relative_url}")
        logger.info(f"URL completa de la carpeta del documento: {second_folder_relative_url}")

        if carpeta_existe(ctx, first_folder_relative_url, docname):
            carpeta_raiz = {
                "tipo": "C",
                "nombre": docname,
                'url': f"{site_url}/{second_folder_relative_url}",
                "children": []
            }
            lista.append(carpeta_raiz)
            procesa_carpeta(ctx, site_url, second_folder_relative_url, carpeta_raiz)
        else:
            logger.error(f"No se encontró la carpeta secundaria para {docname} en {first_folder_relative_url}")

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
