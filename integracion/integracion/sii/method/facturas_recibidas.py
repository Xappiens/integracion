from zeep import xsd
from zeep import Client, Transport
from zeep.helpers import serialize_object
from requests import Session
from requests_pkcs12 import Pkcs12Adapter
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption
from signxml import XMLSigner, methods
import os
import logging
import datetime
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
    
    # Extraer el contenido del <Body> para la validación
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
    
    # Parse the XML content
    root = etree.fromstring(xml_content.encode('utf-8'))

    # Convert the private key and certificate to PEM format
    private_key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=NoEncryption()
    ).decode('utf-8')

    cert_pem = certificate.public_bytes(Encoding.PEM).decode('utf-8')

    # Sign the XML
    signer = XMLSigner(method=methods.enveloped, digest_algorithm='sha256')
    signed_root = signer.sign(root, key=private_key_pem, cert=cert_pem)

    logger.info("XML firmado con éxito")

    # Verificar que el campo "Cabecera" sigue presente
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

    # Crear el elemento root con los namespaces correctos
    envelope = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope", nsmap={
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "siiLR": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd",
        "sii": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd"
    })
    body = etree.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
    root = etree.SubElement(body, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}SuministroLRFacturasRecibidas")

    # Crear el header
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

    # Crear registros para las facturas
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
        num_factura.text = str(factura.name)
        fecha = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaExpedicionFacturaEmisor")
        fecha.text = factura.posting_date.strftime('%d-%m-%Y')

        factura_recibida = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}FacturaRecibida")
        tipo_factura = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoFactura")
        tipo_factura_value = factura.custom_tipo_factura.split(":")[0].strip() if factura.custom_tipo_factura else "F1"
        tipo_factura.text = tipo_factura_value # Extraer el código antes de los dos puntos y eliminar espacios en blanco
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
            base_imponible_inversion.text = "0"
            cuota_soportada_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
            cuota_soportada_inversion.text = "0"
        else:
            for tax in factura.taxes:
                detalle_iva_inversion = etree.SubElement(inversion_sujeto_pasivo, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
                tipo_impositivo_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
                tipo_impositivo_inversion.text = str(tax.rate or 0)
                base_imponible_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
                base_imponible_inversion.text = str(tax.tax_base or 0)
                cuota_soportada_inversion = etree.SubElement(detalle_iva_inversion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
                cuota_soportada_inversion.text = str(tax.tax_amount or 0)

        desglose_iva = etree.SubElement(desglose_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseIVA")
        if not factura.taxes:
            detalle_iva = etree.SubElement(desglose_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
            tipo_impositivo = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
            tipo_impositivo.text = "0"
            base_imponible = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
            base_imponible.text = "0"
            cuota_soportada = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
            cuota_soportada.text = "0"
        else:
            for tax in factura.taxes:
                detalle_iva = etree.SubElement(desglose_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
                tipo_impositivo = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
                tipo_impositivo.text = str(tax.rate or 0)
                base_imponible = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
                base_imponible.text = str(tax.tax_base or 0)
                cuota_soportada = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaSoportada")
                cuota_soportada.text = str(tax.tax_amount or 0)
        
        # Sumar CuotaSoportada para el cálculo de CuotaDeducible
        if not factura.taxes:
            cuota_deducible_valor = 0
        else:
            cuota_soportada_total = sum([float(tax.tax_amount) for tax in factura.taxes if tax.tax_amount > 0])
            cuota_deducible_valor = min(float(factura.grand_total), cuota_soportada_total + 1)

        contraparte = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Contraparte")
        nombre_proveedor = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NombreRazon")
        nombre_proveedor.text = str(factura.supplier_name)
        nif_proveedor = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
        nif_proveedor.text = str(factura.tax_id)

        fecha_reg_contable = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaRegContable")
        fecha_reg_contable.text = factura.posting_date.strftime('%d-%m-%Y')
        
        cuota_deducible = etree.SubElement(factura_recibida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaDeducible")
        cuota_deducible.text = str(cuota_deducible_valor)

    logger.info("XML construido con éxito")
    return etree.tostring(envelope, pretty_print=True, xml_declaration=True, encoding='UTF-8')

def guardar_xml(xml_firmado, filename):
    logger.info(f"Guardando el XML firmado en {filename}")
    with open(filename, 'wb') as f:  # Usar 'wb' para escribir bytes
        f.write(xml_firmado)
    logger.info("XML guardado con éxito")

def enviar_xml_a_aeat(xml_firmado, p12_file_path, p12_password):
    """
    Envía el XML firmado al servicio web de la AEAT.

    :param xml_firmado: El contenido del XML firmado que se va a enviar.
    :param p12_file_path: La ruta al archivo del certificado PFX.
    :param p12_password: La contraseña del archivo del certificado PFX.
    :return: La respuesta de la AEAT.
    """
    logger.info("Enviando XML firmado a la AEAT")
    try:
        # Crear una sesión de requests
        session = Session()
        # Adjuntar el certificado PFX
        session.mount('https://', Pkcs12Adapter(pkcs12_filename=p12_file_path, pkcs12_password=p12_password))

        # Crear el cliente del servicio web con la configuración del certificado
        transport = Transport(session=session)
        client = Client(wsdl=wsdl_recibidas, transport=transport)

        # Parsear el XML firmado
        signed_xml_element = etree.fromstring(xml_firmado)

        # Extraer los elementos necesarios del XML firmado
        cabecera = signed_xml_element.find('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Cabecera')
        registros = signed_xml_element.findall('.//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}RegistroLRFacturasRecibidas')

        # Preparar la estructura de datos para Zeep
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

        # Llamar al servicio SOAP con los parámetros correctos
        respuesta = client.service.SuministroLRFacturasRecibidas(**datos_a_enviar)

        # Loggear la respuesta
        logger.info("XML enviado con éxito")
        logger.info(f"Respuesta de la AEAT: {respuesta}")

        return respuesta

    except Exception as e:
        logger.error(f"Error al enviar el XML a la AEAT: {e}")
        raise

def enviar_facturas_recibidas(docnames):
    logger.info("Iniciando el proceso de envío de facturas recibidas")
    
    # Asegurarse de que docnames sea una lista
    if isinstance(docnames, str):
        # Si se recibe una cadena, quita los corchetes y descompónla en una lista
        docnames = docnames.strip("[]").replace('"', '').replace("'", "").split(",")
    
    # Obtener cada factura basada en el nombre de documento
    facturas = []
    for docname in docnames:
        docname = docname.strip()  # Elimina espacios en blanco al inicio y al final
        factura = get_doc('Purchase Invoice', docname)
        if factura:
            facturas.append(factura)
        else:
            logger.error(f"Factura de Compra [{docname}] no encontrada")
            return {"error": f"Factura de Compra [{docname}] no encontrada"}  # Salir si una factura no se encuentra
    
    xml_data = construir_xml_recibidas(facturas)

    xsd_path = '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/WSDL/SuministroLR.xsd'

    # Validar el XML generado con el XSD
    try:
        validate_xml(xml_data, xsd_path)
    except Exception as e:
        logger.error(f"Error en la validación del XML: {e}")
        return {"error": f"Error en la validación del XML: {e}"}

    # Obtener la empresa de la primera factura
    empresa = facturas[0].company
    logger.info(f"Empresa detectada: {empresa}")
    
    # Obtener el certificado correspondiente a la empresa
    certificado_info = certificados.get(empresa)
    if not certificado_info:
        logger.error(f"No se encontró un certificado para la empresa {empresa}")
        return {"error": f"No se encontró un certificado para la empresa {empresa}"}
    
    p12_file_path = certificado_info['ruta']
    p12_password = certificado_info['password']
    
    # Cargar el certificado
    private_key, certificate = load_certificate(p12_file_path, p12_password)
    
    # Firmar el XML
    xml_firmado = sign_xml(xml_data.decode('utf-8'), private_key, certificate)
    
    # Enviar el XML firmado a la AEAT
    try:
        respuesta, datos_a_enviar = enviar_xml_a_aeat(xml_firmado, p12_file_path, p12_password)
        logger.info(f"Respuesta de la AEAT (tipo): {type(respuesta)}")
        logger.info(f"Datos enviados: {datos_a_enviar}")
        respuesta_dict = serialize_object(respuesta)
        logger.info(f"Respuesta convertida: {respuesta_dict}")
        return {"success": True, "respuesta": respuesta_dict, "datos_enviados": datos_a_enviar}
    except Exception as e:
        logger.error(f"Error al enviar el XML a la AEAT: {e}")
        return {"error": f"Error al enviar el XML a la AEAT: {e}"}
    
    logger.info("Proceso de envío de facturas recibidas finalizado")
