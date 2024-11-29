import os
import json
import logging
from datetime import datetime, timedelta
from urllib.parse import quote
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from lxml import etree
import frappe
import pandas as pd
from frappe import _
import requests
from dataclasses import dataclass
import unicodedata
import re

def remove_accents(input_str):
    # Normalize the string to decompose the accents from the characters
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    # Filter out any non-ASCII characters (this removes accents)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# Leer credenciales desde el archivo de configuración del sitio
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
sharepoint_base_url = "https://grupoatu365.sharepoint.com/sites/DepartamentodeAdministracin2-Contabilidad/Shared%20Documents/Contabilidad/Cuaderno34%20-%20Facturas%20de%20Venta"

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/generate_c34_venta.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

def get_customer_iban(client_name, company):
    # Consultar la cuenta bancaria que tiene un enlace al cliente
    bank_accounts = frappe.get_all("Bank Account", filters={
        "party_type": "Customer",
        "party": client_name
    }, fields=["iban", "company"])

    if not bank_accounts:
        # Si no se encuentra el IBAN en las cuentas bancarias del cliente, buscar el default_bank_account
        default_bank_account = frappe.get_value("Customer", client_name, "default_bank_account")
        if default_bank_account:
            # Obtener el IBAN de la cuenta bancaria predeterminada
            iban = frappe.get_value("Bank Account", default_bank_account, "iban")
            if iban:
                return {"iban": iban}
        
        return ""  # Devolver un valor vacío si no se encuentra el IBAN en ninguna parte

    # Filtrar cuentas bancarias por la empresa específica
    filtered_accounts = [account for account in bank_accounts if account.get("company") == company]

    if filtered_accounts:
        return filtered_accounts[0].iban
    else:
        return bank_accounts[0].iban  # Si no hay coincidencia con la empresa, devolver el primero disponible


def change_status_to_remesa_emitida(sales_invoice_name, remesa_name):
    try:
        # Obtener el documento de la factura de compra
        doc = frappe.get_doc("Sales Invoice", sales_invoice_name)

        # Establecer el campo custom_remesa_emitida a True
        doc.custom_remesa_emitida = 1

        # Establecer el enlace a la remesa
        doc.custom_remesa = remesa_name

        # Marcar la factura como pagada


        # Establecer el modo de pago desde el cliente
        customer_custom_modo_de_cobro = frappe.get_value("Customer", doc.customer, "custom_modo_de_cobro")
        doc.custom_modo_de_cobro = customer_custom_modo_de_cobro

        # Obtener la cuenta bancaria predeterminada para el modo de pago
        default_account = frappe.get_value("Mode of Payment Account", {
            "parent": customer_custom_modo_de_cobro,
            "company": doc.company
        }, "default_account")

        # Asignar la cuenta bancaria predeterminada si está disponible
        if default_account:
            doc.cash_bank_account = default_account

        doc.paid_amount = doc.outstanding_amount

        if doc.docstatus == 0:
            # Guardar el documento para desencadenar el cambio de estado
            doc.save()
            logger.info(f"Estado de la factura {sales_invoice_name} cambiado a 'Remesa Emitida'")
        elif doc.docstatus == 1:
            # Si la factura está validada, solo marcar los campos personalizados
            doc.db_set('custom_remesa_emitida', 1)
            doc.db_set('custom_remesa', remesa_name)

            if default_account:
                doc.db_set('cash_bank_account', default_account)
            doc.db_set('paid_amount', doc.outstanding_amount)

    except Exception as e:
        logger.error(f"Error al cambiar el estado de la factura {sales_invoice_name}: {e}")

@frappe.whitelist()
def generate_c34_venta(invoice_data=None):
    logger.info("Inicio de la generación de Cuaderno 34")

    try:
        # Deserializar el JSON recibido
        invoice_names = json.loads(invoice_data) if invoice_data else []

        if invoice_names:
            logger.debug(f"Procesando facturas específicas: {invoice_names}")

            # Aplicar el filtro solo a las facturas seleccionadas
            filtered_invoices = frappe.get_all("Sales Invoice", filters={
                "name": ["in", invoice_names],
                "custom_aprobada_para_cobro": 1,
                "custom_remesa_emitida": 0,
                "docstatus": ["!=", 2]
            }, fields=["name"])

            # Si no se encuentran facturas después del filtro, no hacer nada
            if not filtered_invoices:
                logger.warning("No se encontraron facturas que cumplan los criterios.")
                return
        else:
            # Si no se seleccionan facturas, obtener todas las facturas aprobadas
            filtered_invoices = frappe.get_all("Sales Invoice", filters={
                "custom_aprobada_para_cobro": 1,
                "custom_remesa_emitida": 0,
                "docstatus": ["!=", 2]
            }, fields=["name"])
            logger.debug(f"Total facturas encontradas: {len(filtered_invoices)}")

    except Exception as e:
        logger.error(f"Error al obtener facturas: {e}")
        return

    invoices_by_company = {}
    for invoice_data in filtered_invoices:
        try:
            invoice = frappe.get_doc("Sales Invoice", invoice_data["name"])
            logger.debug(f"Procesando factura {invoice.name}")

            custom_modo_de_cobro = frappe.get_value("Customer", invoice.customer, "custom_modo_de_cobro")
            if custom_modo_de_cobro != "Giro bancario":
                logger.debug(f"Factura {invoice.name} ignorada por modo de cobro {custom_modo_de_cobro} {invoice.customer}")
                continue

            company = invoice.company
            if not company:
                logger.error(f"Factura {invoice.name} no tiene una empresa asociada.")
                continue

            if company not in invoices_by_company:
                invoices_by_company[company] = []
            invoices_by_company[company].append(invoice)
            logger.debug(f"Factura {invoice.name} agregada a la empresa {company}")

        except Exception as e:
            logger.error(f"Error al procesar la factura {invoice_data['name']}: {e}")
    
    sharepoint_urls = []
    files = []
    for company, invoices in invoices_by_company.items():
        try:
            company_clean = remove_accents(company)
            abbr = frappe.get_value("Company", company, "abbr")
            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            now_format = datetime.now().strftime("%d-%m-%Y")
            tax_id = frappe.get_value("Company", company, "tax_id")  # Obteniendo el CIF de la empresa
            fichero_id_value = f"C19-{abbr}-{now.replace(':', '')}"
            
            # Crear el elemento principal del XML conforme al estándar SEPA
            root = etree.Element("Document", xmlns="urn:iso:std:iso:20022:tech:xsd:pain.008.001.02")
            cstmr_drct_dbt_initn = etree.SubElement(root, "CstmrDrctDbtInitn")

            # Crear el header del grupo
            grp_hdr = etree.SubElement(cstmr_drct_dbt_initn, "GrpHdr")
            msg_id = etree.SubElement(grp_hdr, "MsgId")
            msg_id.text = fichero_id_value
            cre_dt_tm = etree.SubElement(grp_hdr, "CreDtTm")
            cre_dt_tm.text = now
            nb_of_txs = etree.SubElement(grp_hdr, "NbOfTxs")
            nb_of_txs.text = str(len(invoices))
            ctrl_sum = etree.SubElement(grp_hdr, "CtrlSum")
            ctrl_sum.text = "{:.2f}".format(sum(invoice.grand_total for invoice in invoices))
            initg_pty = etree.SubElement(grp_hdr, "InitgPty")
            nm = etree.SubElement(initg_pty, "Nm")
            nm.text = company_clean
            id_elem = etree.SubElement(initg_pty, "Id")
            org_id = etree.SubElement(id_elem, "OrgId")
            othr = etree.SubElement(org_id, "Othr")
            othr_id = etree.SubElement(othr, "Id")
            othr_id.text = frappe.get_value("Company", company, "tax_id")
            schme_nm = etree.SubElement(othr, "SchmeNm")
            prtry = etree.SubElement(schme_nm, "Prtry")
            prtry.text = "ES"

            # Información de pago
            pmt_inf = etree.SubElement(cstmr_drct_dbt_initn, "PmtInf")
            pmt_inf_id = etree.SubElement(pmt_inf, "PmtInfId")
            pmt_inf_id.text = f"{tax_id} {now_format}"
            pmt_mtd = etree.SubElement(pmt_inf, "PmtMtd")
            pmt_mtd.text = "DD"
            nb_of_txs_pmt_inf = etree.SubElement(pmt_inf, "NbOfTxs")
            nb_of_txs_pmt_inf.text = str(len(invoices))
            ctrl_sum_pmt_inf = etree.SubElement(pmt_inf, "CtrlSum")
            ctrl_sum_pmt_inf.text = "{:.2f}".format(sum(invoice.grand_total for invoice in invoices))
            pmt_tp_inf = etree.SubElement(pmt_inf, "PmtTpInf")
            svc_lvl = etree.SubElement(pmt_tp_inf, "SvcLvl")
            svc_lvl_cd = etree.SubElement(svc_lvl, "Cd")
            svc_lvl_cd.text = "SEPA"
            lcl_instrm = etree.SubElement(pmt_tp_inf, "LclInstrm")
            lcl_instrm_cd = etree.SubElement(lcl_instrm, "Cd")
            lcl_instrm_cd.text = "CORE"
            seq_tp = etree.SubElement(pmt_tp_inf, "SeqTp")
            seq_tp.text = "RCUR"
            reqd_colltn_dt = etree.SubElement(pmt_inf, "ReqdColltnDt")
            reqd_colltn_date = frappe.utils.getdate(frappe.utils.nowdate()) + timedelta(days=4)
            reqd_colltn_dt.text = reqd_colltn_date.strftime('%Y-%m-%d')

            # Acreedor (Cdtr)
            cdtr = etree.SubElement(pmt_inf, "Cdtr")
            cdtr_nm = etree.SubElement(cdtr, "Nm")
            cdtr_nm.text = company_clean

            cdtr_acct = etree.SubElement(pmt_inf, "CdtrAcct")
            cdtr_acct_id = etree.SubElement(cdtr_acct, "Id")
            cdtr_acct_iban = etree.SubElement(cdtr_acct_id, "IBAN")
            default_bank_account = frappe.get_value("Company", company, "default_bank_account")
            iban = frappe.get_value("Bank Account", {"account": default_bank_account}, "iban")
            logger.debug(f"IBAN de la empresa {company}: {iban}")
            cdtr_acct_iban.text = iban.upper()

            # Agente del acreedor (CdtrAgt)
            cdtr_agt = etree.SubElement(pmt_inf, "CdtrAgt")
            fin_instn_id = etree.SubElement(cdtr_agt, "FinInstnId")


            chrg_br = etree.SubElement(pmt_inf, "ChrgBr")
            chrg_br.text = "SLEV"

            # Esquema del acreedor (CdtrSchmeId)
            cdtr_schme_id = etree.SubElement(pmt_inf, "CdtrSchmeId")
            id_elem = etree.SubElement(cdtr_schme_id, "Id")
            prvt_id = etree.SubElement(id_elem, "PrvtId")
            othr = etree.SubElement(prvt_id, "Othr")
            othr_id = etree.SubElement(othr, "Id")
            othr_id.text = frappe.get_value("Company", company, "tax_id")
            schme_nm = etree.SubElement(othr, "SchmeNm")
            prtry = etree.SubElement(schme_nm, "Prtry")
            prtry.text = "ES"

            # Datos de las transacciones (facturas)
            for invoice in invoices:
                customer_cif = frappe.get_value("Customer", invoice.customer, "tax_id")
                ref_mandato = frappe.get_value("Customer", invoice.customer, "customer_name") or customer_cif
                firma_mandato = frappe.utils.nowdate()
                drct_dbt_tx_inf = etree.SubElement(pmt_inf, "DrctDbtTxInf")
                pmt_id = etree.SubElement(drct_dbt_tx_inf, "PmtId")
                end_to_end_id = etree.SubElement(pmt_id, "EndToEndId")
                end_to_end_id.text = invoice.name

                amt = etree.SubElement(drct_dbt_tx_inf, "InstdAmt", Ccy="EUR")
                amt.text = "{:.2f}".format(invoice.grand_total)

                drct_dbt_tx = etree.SubElement(drct_dbt_tx_inf, "DrctDbtTx")
                mndt_rltd_inf = etree.SubElement(drct_dbt_tx, "MndtRltdInf")
                mndt_id = etree.SubElement(mndt_rltd_inf, "MndtId")
                mndt_id.text = ref_mandato # Mandato relacionado con la factura

                dt_of_sgntr = etree.SubElement(mndt_rltd_inf, "DtOfSgntr")
                dt_of_sgntr.text = firma_mandato  # Fecha de la firma del mandato

                dbtr_agt = etree.SubElement(drct_dbt_tx_inf, "DbtrAgt")
                fin_instn_id = etree.SubElement(dbtr_agt, "FinInstnId")  # No necesita BIC

                dbtr = etree.SubElement(drct_dbt_tx_inf, "Dbtr")
                dbtr_nm = etree.SubElement(dbtr, "Nm")
                dbtr_nm.text = invoice.customer_name

                dbtr_acct = etree.SubElement(drct_dbt_tx_inf, "DbtrAcct")
                dbtr_acct_id = etree.SubElement(dbtr_acct, "Id")
                iban_elem = etree.SubElement(dbtr_acct_id, "IBAN")
                iban_customer = get_customer_iban(invoice.customer, invoice.company).upper()
                logger.debug(f"IBAN del cliente {invoice.customer}: {iban_customer}")
                iban_elem.text = iban_customer


                rmt_inf = etree.SubElement(drct_dbt_tx_inf, "RmtInf")
                ustrd = etree.SubElement(rmt_inf, "Ustrd")
                ustrd.text = invoice.name or "Pago de factura"

            # Guardar el XML
            xml_file_path = f"/home/frappe/frappe-bench/sites/erp.grupoatu.com/private/cuaderno/{fichero_id_value}.xml"
            tree = etree.ElementTree(root)
            tree.write(xml_file_path, pretty_print=True, xml_declaration=True, encoding="UTF-8")
            logger.info(f"Archivo XML generado para {company}: {xml_file_path}")

            # Validar el XML contra el XSD
            xsd_file_path = "/home/frappe/frappe-bench/apps/integracion/integracion/integracion/c34_xsd/pain.008.001.02.xsd"
            is_valid, validation_errors = validate_xml_against_xsd(xml_file_path, xsd_file_path)
            if is_valid:
                logger.info(f"El archivo XML {xml_file_path} es válido según el XSD.")
            else:
                logger.error(f"El archivo XML {xml_file_path} no es válido según el XSD: {validation_errors}")
                
                return {"error": "XML validation failed", "details": validation_errors}

            # Generar el archivo Excel
            data_total = 0
            data = []
            for invoice in invoices:
                try:
                    customer_iban = get_customer_iban(invoice.customer, invoice.company).upper()
                    fecha_cobro = frappe.utils.getdate(frappe.utils.nowdate()) + timedelta(days=4)
                    customer_cif = frappe.get_value("Customer", invoice.customer, "tax_id")
                    pais = frappe.get_value("Customer", invoice.customer, "custom_pais")
                    ref_mandato = frappe.get_value("Customer", invoice.customer, "customer_name") or customer_cif
                    residente = "S" if pais and pais.lower() == "es" else "N"

                    data.append({
                        "Nombre cliente": invoice.customer_name,
                        "CIF Cliente": customer_cif,
                        "IBAN Cliente": customer_iban,
                        "Importe Factura": invoice.grand_total,
                        "Objeto de la Factura": invoice.remarks or "Pago de factura",
                        "Fecha de factura": invoice.posting_date.strftime('%d-%m-%Y'),
                        "Residente": residente,
                        "Referencia de Mandato": ref_mandato,
                        "Referencia Adeudo": invoice.name,
                        "Fecha de Cobro": fecha_cobro.strftime('%d-%m-%Y'),
                        "Tipo de Adeudo": "RCUR",
                        "Tipo Transferencia": "SEPA"
                    })
                    logger.debug(f"Datos agregados para la factura {invoice.name} del cliente {invoice.customer_name}")
                    create_payment_entry_for_invoice(invoice)
                    data_total = data_total + float(invoice.grand_total)
                except Exception as e:
                    logger.error(f"Error al procesar la factura {invoice.name}: {e}")
            
            # data.append({ 
            #             "Nombre cliente": "",
            #             "CIF Cliente": "",
            #             "IBAN Cliente": "TOTAL" ,
            #             "Importe Factura": data_total,
            #             "Objeto de la Factura": "",
            #             "Fecha de factura": "",
            #             "Residente": "",
            #             "Referencia de Mandato": "",
            #             "Referencia Adeudo": "",
            #             "Fecha de Cobro": "",
            #             "Tipo de Adeudo": "",
            #             "Tipo Transferencia": ""
            #         })

            df = pd.DataFrame(data)
            excel_file_path = f"/home/frappe/frappe-bench/sites/erp.grupoatu.com/private/cuaderno/{fichero_id_value}.xlsx"
            df.to_excel(excel_file_path, index=False)
            logger.info(f"Archivo Excel generado para {company}: {excel_file_path}")

            # Subir el XML a SharePoint
            xml_sharepoint_url = upload_file_to_sharepoint(xml_file_path, company, fichero_id_value)
            if xml_sharepoint_url:
                #sharepoint_urls.append({"company": company, "xml_url": xml_sharepoint_url})
                logger.debug(f"Archivo XML subido a SharePoint: {xml_sharepoint_url}")

            # Subir el Excel a SharePoint
            excel_sharepoint_url = upload_file_to_sharepoint(excel_file_path, company, fichero_id_value)
            if excel_sharepoint_url:
                sharepoint_urls.append({"company": company, "excel_url": excel_sharepoint_url})
                logger.debug(f"Archivo Excel subido a SharePoint: {excel_sharepoint_url}")

            # Crear la remesa y actualizar el estado de las facturas
            remesa_name = create_remesa(company, invoices, excel_sharepoint_url)
            for invoice in invoices:
                change_status_to_remesa_emitida(invoice.name, remesa_name)
                logger.debug(f"Estado cambiado a 'Remesa Emitida' para la factura {invoice.name}")

            # Eliminar los archivos locales después de subirlos
            if os.path.exists(xml_file_path):
                os.remove(xml_file_path)
                logger.info(f"Archivo local XML {xml_file_path} eliminado después de subirlo a SharePoint")

            if os.path.exists(excel_file_path):
                os.remove(excel_file_path)
                logger.info(f"Archivo local Excel {excel_file_path} eliminado después de subirlo a SharePoint")

        except Exception as e:
            logger.error(f"Error al subir el archivo a SharePoint: {e}")
    logger.info("Urls de SharePoint generadas:" + str(sharepoint_urls))
    return sharepoint_urls

def validate_xml_against_xsd(xml_file_path, xsd_file_path):
    try:
        with open(xsd_file_path, 'rb') as schema_file:
            schema_root = etree.XML(schema_file.read())
        schema = etree.XMLSchema(schema_root)

        with open(xml_file_path, 'rb') as xml_file:
            xml_doc = etree.parse(xml_file)

        schema.assertValid(xml_doc)
        return True, None
    except etree.DocumentInvalid as e:
        return False, str(e)

def create_remesa(company, invoices, sharepoint_url):
    try:
        # Crear un nuevo documento de Remesa
        remesa_doc = frappe.get_doc({
            "doctype": "Remesa Registro",
            "remesa_de": "Sales Invoice",
            "company": company,
            "company_abbr": frappe.get_value("Company", company, "abbr"),
            "fecha": frappe.utils.nowdate(),
            "url": sharepoint_url,
            "facturas": [{"factura": inv.name, "importe": inv.grand_total} for inv in invoices],
            "naming_series": "REM-.{company_abbr}.-.{fecha}.-.####.",
        })
        
        logger.info(f"Remesa doc name: {remesa_doc.name}")
        # Insertar el documento en la base de datos
        remesa_doc.save(ignore_permissions=True)  # Esto validará y guardará el documento en vez de insertarlo directamente.
        
        logger.info(f"Remesa creada: {remesa_doc.name} para la empresa {company}")
        return remesa_doc.name
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="Error al crear Remesa")
        logger.error(f"Error al crear el documento de remesa para {company}: {e}")
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

        if (folder_name in folder_names):
            logger.info(f"La carpeta ya existe: {folder_relative_url}/{folder_name}")
        else:
            new_folder = parent_folder.folders.add(folder_name).execute_query()
            logger.info(f"Carpeta creada: {new_folder.serverRelativeUrl}")
    except Exception as e:
        logger.error(f"Error verificando/creando carpeta en {folder_relative_url}/{folder_name}: {e}")
        raise

def upload_file_to_sharepoint(file_path, company, fichero_id_value):
    logger.info(f"Subiendo archivo {file_path} a SharePoint para la compañía {company} con Cuaderno {fichero_id_value}")
    try:
        if not file_path or not os.path.isfile(file_path):
            logger.error(f"El archivo no existe o no se proporcionó una ruta válida: {file_path}")
            return

        # Extraer la ruta relativa y el nombre del sitio desde la URL completa
        start_idx = sharepoint_base_url.find('/sites/')
        if start_idx == -1:
            logger.error("La URL no contiene '/sites/'. No se puede calcular la ruta relativa.")
            return
        site_url = sharepoint_base_url[:start_idx + len('/sites/') + sharepoint_base_url[start_idx + len('/sites/'):].find('/')]
        site_relative_url = sharepoint_base_url[start_idx:start_idx + len('/sites/') + sharepoint_base_url[start_idx + len('/sites/'):].find('/')]
        relative_path = sharepoint_base_url[start_idx + len(site_relative_url):].lstrip('/')
        logger.info(f"Ruta relativa calculada: {relative_path}")
        logger.info(f"Conectando al contexto del sitio: {site_url}")

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


        # credentials = UserCredential(user_email, user_password)
        # ctx = ClientContext(site_url).with_credentials(credentials)
        ctx = connect_to_sharepoint_with_token(site_url)

        company_folder_name = quote(company)
        cuaderno_folder_name = quote(fichero_id_value)

        # Crear la carpeta de la compañía si no existe
        create_folder_if_not_exists(ctx, relative_path, company_folder_name)

        # Crear la carpeta del Cuaderno 34 dentro de la carpeta de la compañía
        company_folder_relative_url = f"{relative_path}/{company_folder_name}".strip('/')
        create_folder_if_not_exists(ctx, company_folder_relative_url, cuaderno_folder_name)

        with open(file_path, 'rb') as file_content:
            content = file_content.read()

        file_name = os.path.basename(file_path)
        file_url = f"{company_folder_relative_url}/{cuaderno_folder_name}/{file_name}"
        logger.info(f"Intentando subir archivo a: {file_url}")

        try:
            target_folder = ctx.web.get_folder_by_server_relative_url(f"{company_folder_relative_url}/{cuaderno_folder_name}")
            ctx.load(target_folder)
            ctx.execute_query()

            target_folder.upload_file(file_name, content).execute_query()
            logger.info(f"Archivo subido: {file_url}")

            # Devolver la URL de SharePoint
            sharepoint_url = f"{site_url}/{file_url}"
            return sharepoint_url

        except Exception as e:
            logger.error(f"Error al subir archivo a SharePoint: {str(e)}")
            return None
    except Exception as e:
        logger.error(f"Error al subir archivo a SharePoint: {str(e)}")
        return None

def create_payment_entry_for_invoice(invoice):
    try:
        # Verificar si la factura ya ha sido pagada
        if invoice.outstanding_amount == 0:
            logger.info(f"La factura {invoice.name} ya está completamente pagada. No se requiere un Payment Entry.")
            return  # Salir de la función sin crear el Payment Entry

        # Obtener la cuenta por cobrar (debit_to) desde la factura de venta
        receivable_account = invoice.debit_to
        
        # Verificar que la cuenta 'receivable_account' esté configurada como "Receivable"
        if frappe.db.get_value("Account", receivable_account, "account_type") != "Receivable":
            frappe.throw(_("La cuenta asignada no es de tipo 'Receivable'. Verifique la configuración de la cuenta."))

        # Obtener la cuenta bancaria de la empresa para el cobro
        company_bank_account = frappe.get_value("Company", invoice.company, "default_bank_account")

        # Validar que la cuenta bancaria de la empresa esté configurada
        if not company_bank_account:
            frappe.throw(_("No se ha configurado una cuenta bancaria por defecto para la empresa."))

        # Crear el documento de Payment Entry
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "posting_date": frappe.utils.nowdate(),
            "party_type": "Customer",
            "party": invoice.customer,
            "company": invoice.company,
            "mode_of_payment": frappe.get_value("Customer", invoice.customer, "custom_modo_de_cobro"),
            "paid_amount": invoice.grand_total,
            "received_amount": invoice.grand_total,
            "paid_from": receivable_account,  # Cuenta de origen del débito (cuenta por cobrar)
            "paid_from_account_currency": frappe.get_value("Account", receivable_account, "account_currency"),
            "paid_to": company_bank_account,  # Cuenta bancaria de la empresa para recibir el pago
            "paid_to_account_currency": frappe.get_value("Account", company_bank_account, "account_currency"),
            "reference_no": invoice.name,
            "reference_date": invoice.posting_date,
            "references": [
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": invoice.name,
                    "total_amount": invoice.grand_total,
                    "outstanding_amount": invoice.outstanding_amount,
                    "allocated_amount": invoice.outstanding_amount,
                }
            ],
            "currency": invoice.currency,
        })
        
        # Guardar y enviar el Payment Entry
        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()

        logger.info(f"Payment Entry creado para la factura {invoice.name}: {payment_entry.name}")

    except Exception as e:
        logger.error(f"Error al crear Payment Entry para la factura {invoice.name}: {e}")
