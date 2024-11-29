import frappe
import xml.etree.ElementTree as ET
from datetime import datetime
import os
import logging

# Configurar el logger
logger = logging.getLogger(__name__)

handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/subir_nominas.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.ERROR)

# Función principal para procesar el archivo XML
@frappe.whitelist()
def subir_nominas(company, xml_file):
    logger.debug("Iniciando el proceso de subida de nóminas.")
        # Publicar el progreso inicial

    progreso = 1


    if not company:
        logger.error("No se proporcionó una empresa.")
        return {'error': 'La empresa es obligatoria'}

    logger.debug(f"Procesando archivo XML para la empresa: {company}.")

    # Obtener el archivo XML subido
    try:
        file_doc = frappe.get_doc("File", {"file_url": xml_file})
        xml_content = file_doc.get_content()
    except Exception as e:
        logger.error(f"Error al obtener el archivo XML: {str(e)}")
        return {'error': f'Error al obtener el archivo XML: {str(e)}'}

    # Cargar el XML
    try:
        tree = ET.ElementTree(ET.fromstring(xml_content))
        root = tree.getroot()
        logger.debug("XML cargado correctamente.")
    except Exception as e:
        logger.error(f"Error al cargar el XML: {str(e)}")
        return {'error': f'Error al cargar el archivo XML: {str(e)}'}
    
    total_asientos = len(root.findall("./Empresa/Asientos/Asiento")) + 1
    frappe.cache().hset('nominas_progreso', 'total_asientos', total_asientos)
    frappe.cache().hset('nominas_progreso', 'progreso', progreso)
    frappe.publish_realtime(
        "subir_nominas_progress", {"progress": [progreso, total_asientos], "message": "Iniciando la carga del archivo XML..."}, user=frappe.session.user
    )
    progreso += 1
    # Obtener la fecha actual para incluir en los nombres de archivo
    current_date = datetime.now().strftime('%Y-%m-%d')

    # Generar nombres de archivo personalizados con la fecha y el nombre de la empresa
    error_log_filename = f"NOMINAS_{company}_{current_date}_ERROR.log".replace(" ", "_")
    fallo_xml_filename = f"NOMINAS_{company}_{current_date}_ERROR.xml".replace(" ", "_")

    # Crear el archivo de errores
    temp_folder_path = frappe.get_site_path("private", "files")
    error_log_path = os.path.join(temp_folder_path, error_log_filename)

    # Crear el XML de fallos con la misma estructura que el original
    root_fallos = ET.Element("Exportacion", attrib={"Origen": "Nominas", "Destino": "Contabilidad"})
    empresa_fallos = ET.SubElement(root_fallos, "Empresa", attrib={
        "NombreFiscal": root.find('./Empresa').attrib['NombreFiscal'],
        "Identificador": root.find('./Empresa').attrib['Identificador']
    })
    asientos_fallos = ET.SubElement(empresa_fallos, "Asientos")

    # Diccionario para almacenar asientos ya registrados
    asientos_registrados = set()

    # Función para registrar errores en el archivo TXT y XML de fallos
    def log_error_and_register_asiento(asiento, nif, motivo):
        # Registrar el error en el archivo TXT
        fecha_asiento = asiento.attrib['Fecha']
        try:
        # Convertir al formato normalizado
            fecha_normalizada = datetime.strptime(fecha_asiento, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Error en la conversión de fecha: {e}")
            fecha_normalizada = fecha_asiento  # Mantener la fecha original si no se puede convertir


        asiento_id = f"{nif}_{fecha_normalizada}"
        
        logger.debug(f"Registrando asiento fallido: {asiento_id} - {motivo}")

        logger.debug(f"Asientos registrados: {asientos_registrados}")

        # Verificar si el asiento ya fue registrado
        if asiento_id in asientos_registrados:
            logger.warning(f"Asiento ya registrado: {asiento_id}. Evitando duplicación.")
            return  # Si ya fue registrado, no hacer nad
        
        empleado_name = ""

        if frappe.db.exists("Employee", {"custom_dninie_id": nif}):
            empleado = frappe.get_doc("Employee", {"custom_dninie_id": nif})
        elif frappe.db.exists("Employee", {"custom_dninie": nif}):
            empleado = frappe.get_doc("Employee", {"custom_dninie": nif})
        else:
            empleado = None

        if empleado:
            empleado_name = empleado.employee_name

        with open(error_log_path, 'a') as f:
            f.write(f"Empleado {nif} {empleado_name} {motivo}\n")
            logger.error(f"{nif} {empleado_name} - {motivo}")

        # Registrar el asiento fallido en el XML de fallos
        asiento_fallo = ET.SubElement(asientos_fallos, "Asiento", attrib={
            "Fecha": asiento.attrib['Fecha'],
            "Nif": asiento.attrib['Nif'],
            "Nombre": asiento.attrib['Nombre'],
            "CP": asiento.attrib.get('CP', '')
        })
        for apunte in asiento.findall("Apunte"):
            ET.SubElement(asiento_fallo, "Apunte", attrib=apunte.attrib).text = apunte.text
        asientos_registrados.add(asiento_id)

    # Limpiar el archivo de errores si ya existe
    with open(error_log_path, 'w') as f:
        f.write('Log de errores para la creación de asientos contables desde el XML\n\n')
    logger.debug("Archivo de errores inicializado.")

    # Función para obtener la cuenta padre de empleados (640 o 4751)
    def get_parent_employee_account(cuenta_padre, company):
        parent_account = frappe.get_all('Account', 
                                        filters={'account_number': cuenta_padre, 'company': company, 'is_group': 1}, 
                                        fields=['name', 'account_number', 'parent_account'])
        return parent_account[0] if parent_account else None

    # Función para obtener la cuenta de empleado usando el objeto padre
    def get_employee_account(parent_account, nif, company):
        accounts = frappe.get_all('Account', 
                                  filters={'parent_account': parent_account['name'], 'company': company, 'custom_empleado': nif}, 
                                  fields=['name', 'account_number'])
        return accounts[0] if accounts else None

    # Función para obtener la cuenta hija con el número de cuenta más bajo de las cuentas como 642
    def get_lowest_child_account(parent_account, company):
        child_accounts = frappe.get_all('Account', 
                                        filters={'parent_account': parent_account['name'], 'company': company}, 
                                        fields=['name', 'account_number'], order_by="account_number asc")
        return child_accounts[0] if child_accounts else None

    # Función para obtener el empleado a partir del NIF
    def get_employee(nif):
        # Verifica si existe el empleado con el campo 'custom_dninie_id'
        if frappe.db.exists('Employee', {'custom_dninie_id': nif}):
            # Si existe, obtiene el empleado
            employee = frappe.get_all('Employee', filters={'custom_dninie_id': nif}, fields=['name'])
        elif frappe.db.exists('Employee', {'custom_dninie': nif}):
            # Si no existe en 'custom_dninie_id', verifica si existe con 'custom_dninie'
            employee = frappe.get_all('Employee', filters={'custom_dninie': nif}, fields=['name'])
        elif frappe.db.exists('Employee', {'name': nif}):
            # Verificar si existe el empleado con el nombre (nif)
            employee = frappe.get_all('Employee', filters={'name': nif}, fields=['name'])
        else:
            # Si no existe en ninguno de los campos, devuelve None
            employee = None

        return employee[0] if employee else None


    # **Paso 1: Comprobar y ajustar las cuentas en el XML**
    logger.debug("Comenzando el proceso de validación y ajuste de cuentas.")
        # Continuar el procesamiento
    frappe.publish_realtime(
        "subir_nominas_progress", {"progress": [progreso, total_asientos], "message": "Comprobando cuentas/empleados..."}, user=frappe.session.user
    )
    progreso += 1

    
    for asiento in root.findall("./Empresa/Asientos/Asiento"):
        nif = asiento.attrib['Nif']
        
        # Buscar el empleado en la tabla Employee
        employee = get_employee(nif)
        if not employee:
            logger.warning(f"No se encontró un empleado con NIF: {nif}.")
            log_error_and_register_asiento(asiento, nif, "Empleado no encontrado")
            continue

        # Iterar sobre los apuntes del asiento
        for apunte in asiento.findall("Apunte"):
            cuenta = apunte.attrib['Cuenta']
            cuenta_prefix = cuenta.split('.')[0]

            if cuenta_prefix in ['640', '4751']:
                # Obtener la cuenta padre para 640 o 4751
                parent_account = get_parent_employee_account(cuenta_prefix, company)

                if not parent_account:
                    logger.warning(f"No se encontró cuenta padre para {cuenta_prefix}.")
                    log_error_and_register_asiento(asiento, nif, "No se encontró cuenta padre")
                    break  # Salimos del bucle ya que el asiento completo falla

                # Buscar la cuenta del empleado
                account = get_employee_account(parent_account, nif, company)

                if account:
                    apunte.set('Cuenta', account['account_number'])
                    logger.debug(f"Cuenta del empleado actualizada para el NIF {nif}.")
                else:
                    logger.warning(f"No se encontró cuenta empleado para el NIF {nif}.")
                    log_error_and_register_asiento(asiento, nif, "No se encontró cuenta para el empleado")
                    break  # Salimos del bucle ya que el asiento completo falla

            else:
                # Para otras cuentas (como 642), buscar la primera cuenta hija disponible
                parent_account = frappe.get_all('Account', 
                                                filters={'account_number': cuenta_prefix, 'company': company, 'is_group': 1}, 
                                                fields=['name', 'account_number'])
                if parent_account:
                    parent_account = parent_account[0]
                    # Obtener la cuenta hija con el número de cuenta más bajo
                    account = get_lowest_child_account(parent_account, company)

                    if account:
                        apunte.set('Cuenta', account['account_number'])
                        logger.debug(f"Cuenta hija encontrada para la cuenta {cuenta_prefix}.")
                    else:
                        logger.warning(f"No se encontró cuenta hija para la cuenta {cuenta_prefix}.")
                        log_error_and_register_asiento(asiento, nif, f"No se encontró cuenta hija para empresa {cuenta_prefix}")
                        break  # Salimos del bucle ya que el asiento completo falla

    # **Paso 2: Crear los asientos contables**
    logger.debug("Comenzando el proceso de creación de asientos contables.")
        # Continuar el procesamiento


    for asiento in root.findall("./Empresa/Asientos/Asiento"):
        progreso += 1
        frappe.cache().hset('nominas_progreso', 'progreso', progreso)
        frappe.publish_realtime(
            "subir_nominas_progress", {"progress": [progreso, total_asientos], "message": f"Procesando asiento {progreso} de {total_asientos-1}"}, user=frappe.session.user
        )
        nif = asiento.attrib['Nif']
        posting_date = datetime.strptime(asiento.attrib['Fecha'], '%d/%m/%Y').strftime('%Y-%m-%d')  # Convertir la fecha al formato esperado por Frappe

        concept = f"Nómina {posting_date} para {nif}"

        try:
            # Verificar si el empleado existe antes de crear el asiento
            employee = frappe.get_value("Employee", {"custom_dninie_id": nif}, "name") or \
                       frappe.get_value("Employee", {"custom_dninie": nif}, "name") or \
                       frappe.get_value("Employee", {"name": nif}, "name")

            if not employee:
                log_error_and_register_asiento(asiento, nif, "Empleado no encontrado")
                continue

            # Crear el Journal Entry
            journal_entry = frappe.get_doc({
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "title": concept,
                "company": company,
                "posting_date": posting_date,
                "user_remark": concept,
                "accounts": []
            })

            # Iterar sobre los apuntes del asiento
            total_debit, total_credit = 0, 0  # Para comprobar el balance
            cuenta_valida = False  # Verificación si hay alguna cuenta válida
            for apunte in asiento.findall("Apunte"):
                naturaleza = apunte.attrib['Naturaleza']
                amount = float(apunte.text.replace(',', '.'))  # Tomar el texto del nodo, no como atributo
                account_number = apunte.attrib['Cuenta']

                # Obtener la cuenta usando el número de cuenta y la empresa
                account_name = frappe.get_value("Account", {"account_number": account_number, "company": company}, "name")

                if not account_name:
                    log_error_and_register_asiento(asiento, nif, f"Cuenta no encontrada: {account_number}")
                    continue

                cuenta_valida = True  # Al menos una cuenta válida encontrada
                debit = amount if naturaleza == "DEBE" else 0
                credit = amount if naturaleza == "HABER" else 0

                # Preparar los datos adicionales si la cuenta es de tipo Payable/Receivable
                account_type = frappe.get_value("Account", account_name, "account_type")
                party_type = None
                party = None

                if account_type in ["Payable", "Receivable"]:
                    party_type = "Employee"
                    party = employee  # Usamos el valor del empleado verificado previamente

                # Agregar la transacción al Journal Entry
                journal_entry.append("accounts", {
                    "account": account_name,
                    "debit_in_account_currency": debit,
                    "credit_in_account_currency": credit,
                    "party_type": party_type,
                    "party": party
                })

                total_debit += debit
                total_credit += credit

            # Verificar el balance del asiento
            if not cuenta_valida:
                log_error_and_register_asiento(asiento, nif, "Ninguna cuenta válida encontrada")
                continue

            if round(total_debit, 2) != round(total_credit, 2):
                difference = round(total_debit - total_credit, 2)
                log_error_and_register_asiento(asiento, nif, f"Balance con diferencia de {difference}")
                continue

            # Insertar el Journal Entry
            journal_entry.insert(ignore_permissions=True)
            frappe.db.commit()
            logger.info(f"Journal Entry creado para el NIF {nif}, fecha {posting_date}.")

        except Exception as e:
            log_error_and_register_asiento(asiento, nif, str(e))

        # Continuar el procesamiento
    frappe.cache().hset('nominas_progreso', 'progreso', progreso)
    frappe.publish_realtime(
        "subir_nominas_progress", {"progress": [progreso, total_asientos], "message": "Guardado fallos y registrando en Doctype..."}, user=frappe.session.user
    )

    # Guardar el XML de fallos con la fecha y el nombre de la empresa
    fallo_xml_path = os.path.join(temp_folder_path, fallo_xml_filename)
    fallo_tree = ET.ElementTree(root_fallos)
    fallo_tree.write(fallo_xml_path)

    # Guardar el archivo de errores y el XML generado en la carpeta de files
    error_log_url = frappe.get_doc({
        "doctype": "File",
        "file_name": error_log_filename,
        "file_url": f"/private/files/{error_log_filename}",
        "is_private": 1,
    }).insert().file_url

    fallo_xml_url = frappe.get_doc({
        "doctype": "File",
        "file_name": fallo_xml_filename,
        "file_url": f"/private/files/{fallo_xml_filename}",
        "is_private": 1,
    }).insert().file_url

    create_registro(error_log_url,fallo_xml_url,company,current_date)

    # Devolver las URLs de los archivos generados para que puedan ser descargados en el frontend
    logger.debug("Proceso completado, generando URLs de los archivos.")

    progreso = total_asientos
    frappe.cache().hset('nominas_progreso', 'progreso', progreso)
    frappe.publish_realtime(
        "subir_nominas_progress", {"progress": [total_asientos, total_asientos], "message": "Proceso completado con éxito."}, user=frappe.session.user
    )
    frappe.cache().hdel('nominas_progreso', 'progreso')  # Borrar cuando termine el proceso
    frappe.cache().hdel('nominas_progreso', 'total_asientos')  # Borrar cuando termine el proceso
    return {
        "error_log": error_log_url,
        "fallo_xml": fallo_xml_url
    }

def create_registro(error_log,error_xml,company,date):
    try:
        # Crear un nuevo documento de Remesa
        fallos_doc = frappe.get_doc({
            "doctype": "Nominas Fallos",
            "empresa": company,
            "fecha": date,
            "log": error_log,
            "xml": error_xml
        })
        
        # Insertar el documento en la base de datos
        fallos_doc.insert()
        
        logger.info(f"Registro fallos creado: {fallos_doc.name} para la empresa {company}")
        return fallos_doc.name
    except Exception as e:
        logger.error(f"Error al crear el documento de fallos para {company}: {e}")
        return None

@frappe.whitelist()
def get_nominas_progreso():
    progreso = frappe.cache().hget('nominas_progreso', 'progreso')
    total_asientos = frappe.cache().hget('nominas_progreso', 'total_asientos')

    if progreso and total_asientos:
        return {
            "progreso": int(progreso),
            "total_asientos": int(total_asientos)
        }
    return None
