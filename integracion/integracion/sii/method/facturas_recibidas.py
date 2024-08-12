from zeep import xsd
from zeep import Client, Transport
from requests import Session
from requests_pkcs12 import Pkcs12Adapter
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from signxml import XMLSigner, methods
import os
import logging
import datetime
import frappe
from frappe import get_doc

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/logs/facturas_recibidas.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Ruta al archivo WSDL para facturas recibidas
wsdl_recibidas = '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/WSDL/SuministroFactRecibidas.wsdl'
client_recibidas = Client(wsdl=wsdl_recibidas)

# Definición de los certificados por empresa
certificados = {
    "Academia Técnica Universitaria SL": {
        "ruta": "/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/certificate/ACADEMIA TECNICA.pfx",
        "password": "Grupo@tu#23"
    },
    # Añade aquí más empresas y sus certificados
}

def load_certificate(p12_file_path, p12_password):
    logger.info(f"Cargando el certificado desde {p12_file_path}")
    with open(p12_file_path, 'rb') as f:
        p12_data = f.read()
    private_key, certificate, _ = pkcs12.load_key_and_certificates(p12_data, p12_password.encode())
    logger.info("Certificado cargado con éxito")
    return private_key, certificate

def validate_xml(xml_data, xsd_path):
    logger.info("Validando el XML contra el esquema XSD")
    schema_root = etree.parse(xsd_path)
    schema = etree.XMLSchema(schema_root)
    
    xml_doc = etree.fromstring(xml_data)
    
    body_content = xml_doc.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body/*")
    
    if body_content is None:
        logger.error("No se encontró el elemento Body en el XML")
        raise ValueError("No se encontró el elemento Body en el XML")
    
    try:
        schema.assertValid(body_content)
        logger.info("XML válido según el esquema XSD")
    except etree.DocumentInvalid as e:
        logger.error(f"Error de validación del XML: {e}")
        raise

def sign_xml(xml_content, private_key, certificate):
    logger.info("Firmando el XML")
    
    root = etree.fromstring(xml_content.encode('utf-8'))

    private_key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption()
    ).decode('utf-8')

    cert_pem = certificate.public_bytes(Encoding.PEM).decode('utf-8')

    signer = XMLSigner(method=methods.enveloped, digest_algorithm='sha256')
    signed_root = signer.sign(root, key=private_key_pem, cert=cert_pem)

    logger.info("XML firmado con éxito")

    cabecera_present = signed_root.find(".//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Cabecera")
    if cabecera_present is None:
        logger.error("El campo 'Cabecera' falta en el XML firmado")
        raise ValueError("El campo 'Cabecera' falta en el XML firmado")

    return etree.tostring(signed_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')

def construir_xml_recibidas(facturas):
    logger.info("Construyendo el XML de las facturas recibidas")

    empresa = facturas[0].company
    company_doc = get_doc('Company', empresa)
    nif_titular = company_doc.tax_id

    logger.info(f"NIF del titular: {nif_titular}")

    envelope = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope", nsmap={
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "siiLR": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd",
        "sii": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd"
    })
    body = etree.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
    root = etree.SubElement(body, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}SuministroLRFacturasRecibidas")

    cabecera = etree.SubElement(root, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Cabecera")
    id_version_sii = etree.SubElement(cabecera, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}IDVersionSii")
    id_version_sii.text = "1.1"
    titular = etree.SubElement(cabecera, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Titular")
    razon_social = etree.SubElement(titular, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NombreRazon")
    razon_social.text = company_doc.company_name
    nif_titular_elem = etree.SubElement(titular, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
    nif_titular_elem.text = nif_titular
    tipo_comunicacion = etree.SubElement(cabecera, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoComunicacion")
    tipo_comunicacion.text = "A0"

    for factura in facturas:
        registro = etree.SubElement(root, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}RegistroLRFacturasRecibidas")

        periodo_liquidacion = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}PeriodoLiquidacion")
        ejercicio = etree.SubElement(periodo_liquidacion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Ejercicio")
        ejercicio.text = str(factura.posting_date.year)
        periodo = etree.SubElement(periodo_liquidacion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Periodo")
        periodo.text = str(factura.posting_date.month).zfill(2)

        id_factura = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}IDFactura")
        id_emisor_factura = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}IDEmisorFactura")
        nif_emisor = etree.SubElement(id_emisor_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
        nif_emisor.text = str(factura.tax_id)
        num_factura = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NumSerieFacturaEmisor")
        num_factura.text = str(factura.bill_no)
        fecha = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaExpedicionFacturaEmisor")
        fecha.text = factura.posting_date.strftime('%d-%m-%Y')

        factura_recibida = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}FacturaRecibida")
        tipo_factura = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoFactura")
        tipo_factura_value = factura.custom_tipo_factura.split(":")[0].strip() if factura.custom_tipo_factura else "F1"
        tipo_factura.text = tipo_factura_value
        fecha_operacion = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaOperacion")
        fecha_operacion.text = factura.posting_date.strftime('%d-%m-%Y')
        clave_regimen = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}ClaveRegimenEspecialOTrascendencia")
        clave_regimen_value = factura.custom_clave_regimen.split(":")[0].strip() if factura.custom_clave_regimen else "01"
        clave_regimen.text = clave_regimen_value
        descripcion_operacion = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DescripcionOperacion")
        descripcion_operacion.text = factura.custom_descripcion_factura if factura.custom_descripcion_factura else "Factura de Compra"

        desglose_factura = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseFactura")
        
        inversion_sujeto_pasivo = etree.SubElement(desglose_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}InversionSujetoPasivo")
        if not factura.taxes:
            detalle_iva_inversion = etree.SubElement(inversion_sujeto_pasivo, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
            tipo_impositivo_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
            tipo_impositivo_inversion.text = "0"
            base_imponible_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
            base_imponible_inversion.text = str(round(factura.net_total, 2))
            cuota_soportada_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
            cuota_soportada_inversion.text = "0"
        else:
            for tax in factura.taxes:
                detalle_iva_inversion = etree.SubElement(inversion_sujeto_pasivo, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
                tipo_impositivo_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
                tipo_impositivo_inversion.text = "0"
                base_imponible_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
                base_imponible_inversion.text = str(round(factura.net_total, 2))
                cuota_soportada_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
                cuota_soportada_inversion.text = "0"

        desglose_iva = etree.SubElement(desglose_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseIVA")
        if not factura.taxes:
            detalle_iva = etree.SubElement(desglose_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
            tipo_impositivo = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
            tipo_impositivo.text = "0"
            base_imponible = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
            base_imponible.text = str(round(factura.net_total, 2))
            cuota_soportada = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
            cuota_soportada.text = "0"
        else:
            for tax in factura.taxes:
                detalle_iva = etree.SubElement(desglose_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
                tipo_impositivo = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
                tipo_impositivo.text = "0"
                base_imponible = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
                base_imponible.text = str(round(factura.net_total, 2))
                cuota_soportada = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
                cuota_soportada.text = "0"

        if not factura.taxes:
            cuota_deducible_valor = 0
        else:
            cuota_soportada_total = 0
            cuota_deducible_valor = 0

        contraparte = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Contraparte")
        nombre_proveedor = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NombreRazon")
        nombre_proveedor.text = str(factura.supplier_name)
        nif_proveedor = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
        nif_proveedor.text = str(factura.tax_id)

        fecha_reg_contable = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaRegContable")
        fecha_reg_contable.text = factura.posting_date.strftime('%d-%m-%Y')
        
        cuota_deducible = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaDeducible")
        cuota_deducible.text = str(round(cuota_deducible_valor, 2))

    logger.info("XML construido con éxito")
    return etree.tostring(envelope, pretty_print=True, xml_declaration=True, encoding='UTF-8')



def enviar_xml_a_aeat(xml_firmado, p12_file_path, p12_password):
    logger.info("Enviando XML firmado a la AEAT")
    try:
        session = Session()
        session.mount('https://', Pkcs12Adapter(pkcs12_filename=p12_file_path, pkcs12_password=p12_password))
        transport = Transport(session=session)
        client = Client(wsdl=wsdl_recibidas, transport=transport)
        signed_xml_element = etree.fromstring(xml_firmado)
        cabecera = signed_xml_element.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Cabecera')
        registros = signed_xml_element.findall('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}RegistroLRFacturasRecibidas')

        datos_a_enviar = {
            'Cabecera': {
                'IDVersionSii': cabecera.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}IDVersionSii').text,
                'Titular': {
                    'NombreRazon': cabecera.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NombreRazon').text,
                    'NIF': cabecera.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF').text
                },
                'TipoComunicacion': cabecera.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoComunicacion').text
            },
            'RegistroLRFacturasRecibidas': [
                {
                    'PeriodoLiquidacion': {
                        'Ejercicio': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Ejercicio').text,
                        'Periodo': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Periodo').text,
                    },
                    'IDFactura': {
                        'IDEmisorFactura': {
                            'NIF': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF').text,
                        },
                        'NumSerieFacturaEmisor': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NumSerieFacturaEmisor').text,
                        'FechaExpedicionFacturaEmisor': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaExpedicionFacturaEmisor').text,
                    },
                    'FacturaRecibida': {
                        'TipoFactura': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoFactura').text,
                        'ClaveRegimenEspecialOTrascendencia': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}ClaveRegimenEspecialOTrascendencia').text,
                        'DescripcionOperacion': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DescripcionOperacion').text,
                        'FechaOperacion': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaOperacion').text,
                        'CuotaDeducible': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaDeducible').text,
                        'Contraparte': {
                            'NombreRazon': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NombreRazon').text,
                            'NIF': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF').text
                        },
                        'FechaRegContable': registro.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaRegContable').text,
                        'DesgloseFactura': {
                            'InversionSujetoPasivo': {
                                'DetalleIVA': [
                                    {
                                        'TipoImpositivo': detalle_iva_inversion.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo').text,
                                        'BaseImponible': detalle_iva_inversion.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible').text,
                                        'CuotaSoportada': detalle_iva_inversion.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada').text,
                                    }
                                    for detalle_iva_inversion in registro.findall('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA')
                                ]
                            },
                            'DesgloseIVA': {
                                'DetalleIVA': [
                                    {
                                        'TipoImpositivo': detalle_iva.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo').text,
                                        'BaseImponible': detalle_iva.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible').text,
                                        'CuotaSoportada': detalle_iva.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada').text,
                                    }
                                    for detalle_iva in registro.findall('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA')
                                ]
                            }
                        }
                    }
                } for registro in registros
            ]
        }

        respuesta = client.service.SuministroLRFacturasRecibidas(**datos_a_enviar)
        logger.info("XML enviado con éxito")
        logger.info(f"Respuesta de la AEAT: {respuesta}")

        return respuesta

    except Exception as e:
        logger.error(f"Error al enviar el XML a la AEAT: {e}")
        raise


def guardar_xml(xml_firmado, filename):
    logger.info(f"Guardando el XML firmado en {filename}")
    with open(filename, 'wb') as f:
        f.write(xml_firmado)
    logger.info("XML guardado con éxito")



def enviar_facturas_recibidas(docnames):
    if isinstance(docnames, str):
        docnames = frappe.parse_json(docnames)  # Asegura que sea una lista si se pasa como una cadena JSON
    
    
    facturas_por_empresa = {}
    for docname in docnames:
        factura = get_doc('Purchase Invoice', docname)
        if factura.company not in facturas_por_empresa:
            facturas_por_empresa[factura.company] = []
        facturas_por_empresa[factura.company].append(factura)

    archivos_generados = []

    for empresa, facturas in facturas_por_empresa.items():
        xml_data = construir_xml_recibidas(facturas)

        xsd_path = '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/WSDL/SuministroLR.xsd'

        try:
            validate_xml(xml_data, xsd_path)
        except Exception as e:
            logger.error(f"Error en la validación del XML para la empresa {empresa}: {e}")
            continue

        now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        certificado_info = certificados.get(empresa)
        if not certificado_info:
            logger.error(f"No se encontró un certificado para la empresa {empresa}")
            continue
        
        p12_file_path = certificado_info['ruta']
        p12_password = certificado_info['password']
        
        private_key, certificate = load_certificate(p12_file_path, p12_password)
        
        xml_firmado = sign_xml(xml_data.decode('utf-8'), private_key, certificate)
        
        current_directory = os.path.dirname(os.path.abspath(__file__))
        output_file = os.path.join(current_directory, f'facturas_recibidas_firmadas_{empresa}_{now}.xml')
        guardar_xml(xml_firmado, output_file)

        try:
            respuesta = enviar_xml_a_aeat(xml_firmado, p12_file_path, p12_password)
            logger.info(f"Respuesta de la AEAT para la empresa {empresa}: {respuesta}")
            archivos_generados.append(output_file)
        except Exception as e:
            logger.error(f"Error al enviar el XML a la AEAT para la empresa {empresa}: {e}")

    logger.info("Proceso de envío de facturas recibidas finalizado")
    return archivos_generados
