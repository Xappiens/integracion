import os
import json
import logging
import datetime
from urllib.parse import quote
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from lxml import etree
import frappe
import pandas as pd
from frappe import _

# Leer credenciales desde el archivo de configuración del sitio
site_config = frappe.get_site_config()
user_email = site_config.get('user_sp')
user_password = site_config.get('pass_sp')
sharepoint_base_url = "https://grupoatu365.sharepoint.com/sites/DepartamentodeAdministracin2-Contabilidad/Shared%20Documents/Contabilidad/Cuaderno34%20-%20Facturas%20de%20Compra"

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/generate_c34_compra.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

def get_supplier_iban(supplier_name, company):
    # Consultar la cuenta bancaria que tiene un enlace al proveedor
    bank_accounts = frappe.get_all("Bank Account", filters={
        "party_type": "Supplier",
        "party": supplier_name
    }, fields=["iban", "company"])

    if not bank_accounts:
        # Si no se encuentra el IBAN en las cuentas bancarias del proveedor, buscar el default_bank_account
        default_bank_account = frappe.get_value("Supplier", supplier_name, "default_bank_account")
        if default_bank_account:
            # Obtener el IBAN de la cuenta bancaria predeterminada
            iban = frappe.get_value("Bank Account", default_bank_account, "iban")
            if iban:
                return iban
        
        return ""  # Devolver un valor vacío si no se encuentra el IBAN en ninguna parte

    # Filtrar cuentas bancarias por la empresa específica
    filtered_accounts = [account for account in bank_accounts if account.get("company") == company]

    if filtered_accounts:
        return filtered_accounts[0]
    else:
        return bank_accounts[0] # Si no hay coincidencia con la empresa, devolver el primero disponible


def change_status_to_remesa_emitida(purchase_invoice_name, remesa_name):
    try:
        # Obtener el documento de la factura de compra
        doc = frappe.get_doc("Purchase Invoice", purchase_invoice_name)

        # Establecer el campo custom_remesa_emitida a True
        doc.custom_remesa_emitida = 1

        # Establecer el enlace a la remesa
        doc.custom_remesa = remesa_name

        # Marcar la factura como pagada
        doc.is_paid = 1

        # Establecer el modo de pago desde el proveedor
        supplier_mode_of_payment = frappe.get_value("Supplier", doc.supplier, "mode_of_payment")
        doc.mode_of_payment = supplier_mode_of_payment

        # Obtener la cuenta bancaria predeterminada para el modo de pago
        default_account = frappe.get_value("Mode of Payment Account", {
            "parent": supplier_mode_of_payment,
            "company": doc.company
        }, "default_account")

        # Asignar la cuenta bancaria predeterminada si está disponible
        if default_account:
            doc.cash_bank_account = default_account

        doc.paid_amount = doc.outstanding_amount

        if doc.docstatus == 0:
            # Guardar el documento para desencadenar el cambio de estado
            doc.save()
            logger.info(f"Estado de la factura {purchase_invoice_name} cambiado a 'Remesa Emitida'")
        elif doc.docstatus == 1:
            # Si la factura está validada, solo marcar los campos personalizados
            doc.db_set('custom_remesa_emitida', 1)
            doc.db_set('custom_remesa', remesa_name)
            doc.db_set('is_paid', 1)
            doc.db_set('mode_of_payment', supplier_mode_of_payment)
            if default_account:
                doc.db_set('cash_bank_account', default_account)
            doc.db_set('paid_amount', doc.outstanding_amount)

    except Exception as e:
        logger.error(f"Error al cambiar el estado de la factura {purchase_invoice_name}: {e}")

def create_payment_entry_for_invoice(company, invoice):
    try:
        # Obtener la cuenta bancaria del proveedor utilizando get_supplier_iban
        bank_account_info = get_supplier_iban(invoice.supplier, company)
        bank_account = bank_account_info.get('iban') if bank_account_info else None

        # Crear un nuevo documento de Payment Entry
        payment_entry_doc = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Pay",
            "party_type": "Supplier",
            "company": company,
            "party": invoice.supplier,
            "posting_date": frappe.utils.nowdate(),
            "paid_from": frappe.get_value("Company", company, "default_payable_account"),
            "paid_to": bank_account,
            "paid_amount": invoice.outstanding_amount,
            "received_amount": invoice.outstanding_amount,
            "references": [
                {
                    "reference_doctype": "Purchase Invoice",
                    "reference_name": invoice.name,
                    "due_date": invoice.due_date,
                    "total_amount": invoice.grand_total,
                    "outstanding_amount": invoice.outstanding_amount,
                    "allocated_amount": invoice.outstanding_amount
                }
            ],
        })

        # Insertar y guardar el documento de Payment Entry
        payment_entry_doc.insert(ignore_permissions=True)
        payment_entry_doc.submit()
        logger.info(f"Payment Entry creado: {payment_entry_doc.name} para la empresa {company}")
        return payment_entry_doc.name
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="Error al crear Payment Entry")
        logger.error(f"Error al crear el documento de Payment Entry para {company}: {e}")
        return None

@frappe.whitelist()
def generate_c34_compra(invoice_data=None):
    logger.info("Inicio de la generación de Cuaderno 34")

    try:
        # Deserializar el JSON recibido
        invoice_names = json.loads(invoice_data) if invoice_data else []

        if invoice_names:
            logger.debug(f"Procesando facturas específicas: {invoice_names}")

            # Aplicar el filtro solo a las facturas seleccionadas
            filtered_invoices = frappe.get_all("Purchase Invoice", filters={
                "name": ["in", invoice_names],
                "custom_aprobado_para_pago": 1,
                "custom_remesa_emitida": 0,
                "docstatus": ["!=", 2]
            }, fields=["name"])

            # Si no se encuentran facturas después del filtro, no hacer nada
            if not filtered_invoices:
                logger.warning("No se encontraron facturas que cumplan los criterios.")
                return
        else:
            # Si no se seleccionan facturas, obtener todas las facturas aprobadas
            filtered_invoices = frappe.get_all("Purchase Invoice", filters={
                "custom_aprobado_para_pago": 1,
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
            invoice = frappe.get_doc("Purchase Invoice", invoice_data["name"])
            logger.debug(f"Procesando factura {invoice.name}")

            mode_of_payment = frappe.get_value("Supplier", invoice.supplier, "mode_of_payment")
            if mode_of_payment != "Transferencia bancaria":
                logger.debug(f"Factura {invoice.name} ignorada por modo de pago {mode_of_payment} {invoice.supplier}")
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
            abbr = frappe.get_value("Company", company, "abbr")
            now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            fichero_id_value = f"C34-{abbr}-{now}"
            
            # Crear el elemento principal del XML conforme al estándar SEPA
            root = etree.Element("Document", xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03")
            cstmr_cdt_trf_initn = etree.SubElement(root, "CstmrCdtTrfInitn")

            # Crear el header del grupo
            grp_hdr = etree.SubElement(cstmr_cdt_trf_initn, "GrpHdr")
            msg_id = etree.SubElement(grp_hdr, "MsgId")
            msg_id.text = fichero_id_value
            cre_dt_tm = etree.SubElement(grp_hdr, "CreDtTm")
            cre_dt_tm.text = now
            nb_of_txs = etree.SubElement(grp_hdr, "NbOfTxs")
            nb_of_txs.text = str(len(invoices))
            ctrl_sum = etree.SubElement(grp_hdr, "CtrlSum")
            ctrl_sum.text = str(sum(invoice.grand_total for invoice in invoices))
            initg_pty = etree.SubElement(grp_hdr, "InitgPty")
            nm = etree.SubElement(initg_pty, "Nm")
            nm.text = company
            id_elem = etree.SubElement(initg_pty, "Id")
            org_id = etree.SubElement(id_elem, "OrgId")
            othr = etree.SubElement(org_id, "Othr")
            othr_id = etree.SubElement(othr, "Id")
            othr_id.text = frappe.get_value("Company", company, "tax_id")

            # Información de pago
            pmt_inf = etree.SubElement(cstmr_cdt_trf_initn, "PmtInf")
            pmt_inf_id = etree.SubElement(pmt_inf, "PmtInfId")
            pmt_inf_id.text = f"PMT-{abbr}-{now}"
            pmt_mtd = etree.SubElement(pmt_inf, "PmtMtd")
            pmt_mtd.text = "TRF"
            btch_bookg = etree.SubElement(pmt_inf, "BtchBookg")
            btch_bookg.text = "false"
            nb_of_txs_pmt_inf = etree.SubElement(pmt_inf, "NbOfTxs")
            nb_of_txs_pmt_inf.text = str(len(invoices))
            ctrl_sum_pmt_inf = etree.SubElement(pmt_inf, "CtrlSum")
            ctrl_sum_pmt_inf.text = str(sum(invoice.grand_total for invoice in invoices))
            pmt_tp_inf = etree.SubElement(pmt_inf, "PmtTpInf")
            instr_prty = etree.SubElement(pmt_tp_inf, "InstrPrty")
            instr_prty.text = "NORM"
            svc_lvl = etree.SubElement(pmt_tp_inf, "SvcLvl")
            svc_lvl_cd = etree.SubElement(svc_lvl, "Cd")
            svc_lvl_cd.text = "SEPA"
            reqd_exctn_dt = etree.SubElement(pmt_inf, "ReqdExctnDt")
            reqd_exctn_dt.text = frappe.utils.nowdate()

            # Ordenante
            dbtr = etree.SubElement(pmt_inf, "Dbtr")
            dbtr_nm = etree.SubElement(dbtr, "Nm")
            dbtr_nm.text = company

            # Extraer el texto plano del campo HTML address_html
            #address_html = frappe.get_value("Company", company, "address_html")
            #soup = BeautifulSoup(address_html, 'html.parser')
            #address_text = soup.get_text(separator=", ")

            dbtr_pstl_adr = etree.SubElement(dbtr, "PstlAdr")
            dbtr_ctry = etree.SubElement(dbtr_pstl_adr, "Ctry")
            dbtr_ctry.text = "ES"
            dbtr_adr_line = etree.SubElement(dbtr_pstl_adr, "AdrLine")
            #dbtr_adr_line.text = address_text
            dbtr_adr_line.text = "address_text"
            dbtr_id = etree.SubElement(dbtr, "Id")
            dbtr_org_id = etree.SubElement(dbtr_id, "OrgId")
            dbtr_othr = etree.SubElement(dbtr_org_id, "Othr")
            dbtr_othr_id = etree.SubElement(dbtr_othr, "Id")
            dbtr_othr_id.text = frappe.get_value("Company", company, "tax_id")
            dbtr_acct = etree.SubElement(pmt_inf, "DbtrAcct")
            dbtr_acct_id = etree.SubElement(dbtr_acct, "Id")
            dbtr_acct_iban = etree.SubElement(dbtr_acct_id, "IBAN")
            dbtr_acct_iban.text = frappe.get_value("Company", company, "default_bank_account")
            dbtr_agt = etree.SubElement(pmt_inf, "DbtrAgt")
            dbtr_fin_instn_id = etree.SubElement(dbtr_agt, "FinInstnId")
            # dbtr_bic = etree.SubElement(dbtr_fin_instn_id, "BIC")
            # dbtr_bic.text = frappe.get_value("Company", company, "bic")

            data = []
            for invoice in invoices:
                try:
                    supplier_bank = get_supplier_iban(invoice.supplier,company)
                    supplier_iban = supplier_bank.get('iban') if supplier_bank else None
                    supplier_cif = frappe.get_value("Supplier", invoice.supplier, "tax_id")
                    
                    data.append({
                        "Nº Factura Proveedor": invoice.bill_no,
                        "Nombre proveedor": invoice.supplier_name,
                        "CIF Proveedor": supplier_cif,
                        "IBAN Proveedor": supplier_iban,
                        "Importe Factura": invoice.outstanding_amount,
                        "Objeto de la Factura": invoice.remarks or "Pago de factura",
                        "Fecha de factura": invoice.bill_date.strftime('%Y-%m-%d'),
                        "Tipo Transferencia" : "SEPA" 
                    })
                    logger.debug(f"Datos agregados para la factura {invoice.name} del proveedor {invoice.supplier_name}")
                except Exception as e:
                    logger.error(f"Error al procesar la factura {invoice.name}: {e}")

            df = pd.DataFrame(data)
            file_path = f"/home/frappe/frappe-bench/sites/erp.grupoatu.com/private/cuaderno/{fichero_id_value}.xlsx"
            df.to_excel(file_path, index=False)
            logger.info(f"Archivo Excel generado para {company}: {file_path}")

            sharepoint_url = upload_file_to_sharepoint(file_path, company, fichero_id_value)
            if sharepoint_url:
                sharepoint_urls.append({"company": company, "url": sharepoint_url})
                logger.debug(f"Archivo subido a SharePoint: {sharepoint_url}")

                remesa_name = create_remesa(company, invoices, sharepoint_url)
                for invoice in invoices:
                    change_status_to_remesa_emitida(invoice.name, remesa_name)
                    logger.debug(f"Estado cambiado a 'Remesa Emitida' para la factura {invoice.name}")

                    create_payment_entry_for_purchase_invoice(invoice)
                    # Crear el registro de Payment Entry para cada factura
                    # payment_entry_name = create_payment_entry_for_invoice(company, invoice)
                    # if payment_entry_name:
                    #     logger.info(f"Payment Entry creado exitosamente: {payment_entry_name} para la factura {invoice.name}")
                    # else:
                    #     logger.error(f"No se pudo crear el Payment Entry para la factura {invoice.name}")
                
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Archivo local {file_path} eliminado después de subirlo a SharePoint")
        except Exception as e:
            logger.error(f"Error al subir el archivo {file_path} a SharePoint: {e}")

    return sharepoint_urls


def create_remesa(company, invoices, sharepoint_url):
    try:
        # Crear un nuevo documento de Remesa
        remesa_doc = frappe.get_doc({
            "doctype": "Remesa Registro",
            "remesa_de": "Purchase Invoice",
            "company": company,
            "company_abbr": frappe.get_value("Company", company, "abbr"),
            "fecha": frappe.utils.nowdate(),
            "url": sharepoint_url,
            "facturas": [{"factura": inv.name, "importe": inv.outstanding_amount} for inv in invoices],
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

        if folder_name in folder_names:
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

        credentials = UserCredential(user_email, user_password)
        ctx = ClientContext(site_url).with_credentials(credentials)

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

def create_payment_entry_for_purchase_invoice(invoice):
    try:
        # Obtener la cuenta de débito desde la factura de compra
        debit_account = frappe.get_value("Company", invoice.company, "default_payable_account")
        
        # Obtener la cuenta de pago por defecto de la compañía
        default_payment_account = frappe.get_value("Company", invoice.company, "default_payable_account")
        
        # Crear el documento de Payment Entry
        payment_entry = frappe.get_doc({
            "doctype": "Payment Entry",
            "payment_type": "Pay",
            "posting_date": frappe.utils.nowdate(),
            "party_type": "Supplier",
            "party": invoice.supplier,
            "company": invoice.company,
            "mode_of_payment": frappe.get_value("Supplier", invoice.supplier, "mode_of_payment"),
            "paid_amount": invoice.grand_total,
            "received_amount": invoice.grand_total,
            "paid_from": debit_account,  # Cuenta de origen del pago
            "paid_to": default_payment_account,  # Cuenta de pago
            "paid_to_account_currency": "EUR",  # Moneda en EUR
            "bank_account": frappe.get_value("Company", invoice.company, "default_bank_account"),  # Cuenta bancaria por defecto de la empresa
            "party_bank_account": frappe.get_value("Supplier", invoice.supplier, "default_bank_account"),  # Cuenta bancaria del proveedor
            "reference_no": invoice.name,
            "reference_date": invoice.posting_date,
            "references": [
                {
                    "reference_doctype": "Purchase Invoice",
                    "reference_name": invoice.name,
                    "total_amount": invoice.grand_total,
                    "outstanding_amount": invoice.outstanding_amount,
                    "allocated_amount": invoice.grand_total,
                }
            ],
            "currency": "EUR",  # Moneda definida a EUR
        })
        
        # Guardar el Payment Entry
        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()
        
        logger.info(f"Payment Entry creado para la factura {invoice.name}: {payment_entry.name}")

    except Exception as e:
        logger.error(f"Error al crear Payment Entry para la factura {invoice.name}: {e}")