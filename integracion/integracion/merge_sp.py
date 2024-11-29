import os
import logging
from logging.handlers import RotatingFileHandler
from urllib.parse import urlsplit
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from dataclasses import dataclass
import frappe
import re
import requests

# Configurar el logger
logger = logging.getLogger(__name__)
handler = RotatingFileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/smerge_folders.log', maxBytes=5 * 1024 * 1024, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Leer credenciales desde el archivo de configuración del sitio
site_config = frappe.get_site_config()
user_email = site_config.get('user_sp')
user_password = site_config.get('pass_sp')
id_cliente = site_config.get('id_sp_client')
secret_sp = site_config.get('secret_sp')
tenant_id = site_config.get('tenant_sp')
auth_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
# Función para obtener el token de acceso

@dataclass
class Token:
    tokenType: str
    accessToken: str

# Función para obtener el token de acceso
def obtener_token_de_acceso():
    data = {
        'grant_type': 'client_credentials',
        'client_id': id_cliente,
        'client_secret': secret_sp,
        'scope': 'https://graph.microsoft.com/.default'
    }

    response = requests.post(auth_url, data=data)
    if response.status_code == 200:
        token_info = response.json()
        access_token = Token(tokenType="Bearer", accessToken=token_info['access_token'])
        logger.info("Autenticación exitosa. Token obtenido.")
        return access_token
    else:
        logger.error(f"Error de autenticación: {response.json()}")
        return None: {response.json()}")
        return None

# Modificar la conexión a SharePoint para usar el token
def connect_to_sharepoint_with_token(site_url):
    access_token = obtener_token_de_acceso()
    if access_token:
        ctx = ClientContext(site_url).with_access_token(access_token)
        return ctx
    else:
        logger.error("No se pudo obtener el token de acceso.")
        return None


# Obtener la URL base y la ruta relativa desde 'Bibliotecas SP' para 'Job Offer'
def get_sharepoint_urls():
    try:
        biblioteca_name = frappe.db.get_value('Bibliotecas SP', {'documento': 'Job Offer'}, 'name')
        if not biblioteca_name:
            logger.error("No se encontró ningún documento en 'Bibliotecas SP' para 'Job Offer'.")
            return None, None

        doc_biblioteca = frappe.get_doc('Bibliotecas SP', biblioteca_name)
        full_url = doc_biblioteca.url_sp

        # Extraer `site_url` y `parent_relative_url`
        split_url = urlsplit(full_url)
        site_url = f"{split_url.scheme}://{split_url.netloc}/sites/{split_url.path.split('/')[2]}"
        parent_relative_url = split_url.path

        logger.info(f"URL base del sitio (site_url): {site_url}")
        logger.info(f"Ruta relativa de la carpeta de trabajo (parent_relative_url): {parent_relative_url}")
        return site_url, parent_relative_url

    except Exception as e:
        logger.error(f"Error al obtener la URL de SharePoint: {e}")
        return None, None

def sanitize_name(name):
    """
    Reemplaza caracteres prohibidos en SharePoint con un guion,
    elimina dobles espacios, y quita espacios al inicio o final.
    """
    sanitized_name = name.translate(str.maketrans({
        '*': '-', '"': '-', ':': '-', '<': '-', '>': '-', '?': '-', '/': '-', '\\': '-', '|': '-', ',': '-', '.': '-'
    }))
    sanitized_name = re.sub(r'\s+', ' ', sanitized_name)
    return sanitized_name.strip()

def get_dni_from_job_offer(folder_name):
    """
    Obtiene el DNI o custom_empleado de una Job Offer leyendo los documentos
    desde Frappe.
    """
    try:
        job_offer = frappe.get_doc("Job Offer", folder_name)
        return job_offer.get("custom_dninie") or job_offer.get("custom_empleado")
    except Exception as e:
        logger.error(f"Error al obtener datos de la Job Offer {folder_name}: {e}")
        return None

def move_job_offer_folders(ctx, old_folder_name, new_folder_name, parent_relative_url):
    """
    Mueve las subcarpetas de ofertas de trabajo de la carpeta antigua a la carpeta nueva en SharePoint.
    """
    try:
        old_folder = ctx.web.get_folder_by_server_relative_url(f"{parent_relative_url}/{old_folder_name}")
        new_folder = ctx.web.get_folder_by_server_relative_url(f"{parent_relative_url}/{new_folder_name}")
        ctx.load(old_folder)
        ctx.load(new_folder)
        ctx.execute_query()

        # Mover cada subcarpeta de la carpeta antigua a la nueva
        subfolders = old_folder.folders
        ctx.load(subfolders)
        ctx.execute_query()
        for subfolder in subfolders:
            subfolder_name = subfolder.properties["Name"]
            logger.info(f"Moviendo carpeta {subfolder_name} de {old_folder_name} a {new_folder_name}")
            subfolder.move_to(f"{new_folder.serverRelativeUrl}/{subfolder_name}").execute_query()

        logger.info(f"Contenido de {old_folder_name} movido a {new_folder_name} correctamente.")
    except Exception as e:
        logger.error(f"Error al mover contenido de {old_folder_name} a {new_folder_name}: {e}")

def delete_folder_if_empty(ctx, folder_name, parent_relative_url):
    """
    Elimina una carpeta si está vacía.
    """
    try:
        folder = ctx.web.get_folder_by_server_relative_url(f"{parent_relative_url}/{folder_name}")
        ctx.load(folder)
        ctx.execute_query()

        # Verificar si la carpeta tiene subcarpetas o archivos
        subfolders = folder.folders
        files = folder.files
        ctx.load(subfolders)
        ctx.load(files)
        ctx.execute_query()

        # Si la carpeta está vacía, eliminarla
        if len(subfolders) == 0 and len(files) == 0:
            folder.delete_object()
            ctx.execute_query()
            logger.info(f"Carpeta vacía eliminada: {folder_name}")
        else:
            logger.info(f"La carpeta {folder_name} no está vacía y no se eliminará.")

    except Exception as e:
        logger.error(f"Error al eliminar la carpeta {folder_name}: {e}")

def main():
    # Obtener `site_url` y `parent_relative_url` desde Bibliotecas SP
    site_url, parent_relative_url = get_sharepoint_urls()
    if not site_url or not parent_relative_url:
        raise Exception("No se pudo obtener la URL de SharePoint correctamente.")

    # Conectar a SharePoint
    credentials = UserCredential(user_email, user_password)
    # ctx = ClientContext(site_url).with_credentials(credentials)
    ctx = connect_to_sharepoint_with_token(site_url)

    # Obtener la carpeta raíz en SharePoint
    root_folder = ctx.web.get_folder_by_server_relative_url(parent_relative_url)
    ctx.load(root_folder)
    ctx.execute_query()

    folders = root_folder.folders
    ctx.load(folders)
    ctx.execute_query()

    # Crear un diccionario para almacenar las carpetas antiguas y nuevas
    folder_dict = {}

    for folder in folders:
        folder_name = folder.properties["Name"]
        sanitized_name = sanitize_name(folder_name)

        # Cambiar el patrón de coincidencia para buscar solo el primer guion
        match = re.match(r"^(.+?) - (.+)$", sanitized_name)

        # Si hay coincidencia, es una carpeta "nueva" con DNI
        if match:
            base_name, dni = match.groups()
            folder_dict.setdefault(base_name, {})["new"] = sanitized_name  # Almacenar como "new"


        # Si no hay coincidencia, es una carpeta "antigua" sin DNI
        else:
            base_name = sanitized_name
            folder_dict.setdefault(base_name, {})["old"] = sanitized_name  # Almacenar como "old"
            logger.info(f"Carpeta antigua encontrada: {sanitized_name}")



    # Para cada carpeta antigua, buscar y mover su contenido a la nueva con DNI
    for base_name, folders in folder_dict.items():
        if "old" in folders and "new" in folders:
            old_folder_name = folders["old"]
            new_folder_name = folders["new"]
            logger.info(f"Procesando carpeta antigua: {old_folder_name} y nueva: {new_folder_name}")

            # Obtener el DNI o empleado desde una Job Offer en la carpeta antigua
            old_folder = ctx.web.get_folder_by_server_relative_url(f"{parent_relative_url}/{old_folder_name}")
            ctx.load(old_folder)
            ctx.execute_query()
            subfolders = old_folder.folders
            ctx.load(subfolders)
            ctx.execute_query()

            # Buscar una subcarpeta y obtener el DNI o custom_empleado
            dni_or_empleado = None
            for subfolder in subfolders:
                job_offer_name = subfolder.properties["Name"]
                dni_or_empleado = get_dni_from_job_offer(job_offer_name)
                logger.info(f"Obteniendo DNI o custom_empleado de {job_offer_name}: {dni_or_empleado}")
                if dni_or_empleado:
                    break  # Asumimos que todas las subcarpetas son del mismo empleado

            # Mover contenido si se encontró el DNI o custom_empleado correspondiente
            if dni_or_empleado and dni_or_empleado in new_folder_name:
                logger.info(f"Iniciando merge de {old_folder_name} a {new_folder_name}")
                move_job_offer_folders(ctx, old_folder_name, new_folder_name, parent_relative_url)
                
                # Eliminar la carpeta antigua si quedó vacía
            delete_folder_if_empty(ctx, old_folder_name, parent_relative_url)


# Ejecutar el script principal
main()
