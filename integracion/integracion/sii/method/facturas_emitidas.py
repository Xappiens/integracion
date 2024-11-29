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
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/logs/facturas_emitidas.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Ruta al archivo WSDL para facturas emitidas
wsdl_emitidas = '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/WSDL/SuministroFactEmitidas.wsdl'
client_emitidas = Client(wsdl=wsdl_emitidas)

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
    # Load private key and certificate
    private_key, certificate, _ = pkcs12.load_key_and_certificates(p12_data, p12_password.encode())
    logger.info("Certificado cargado con éxito")
    return private_key, certificate

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

    # Ensure the "Cabecera" field is present
    cabecera_present = signed_root.find(".//{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Cabecera")
    if cabecera_present is None:
        logger.error("El campo 'Cabecera' falta en el XML firmado")
        raise ValueError("El campo 'Cabecera' falta en el XML firmado")

    return etree.tostring(signed_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')

def validate_xml(xml_data, xsd_path):
    """
    Valida el contenido del <Body> de un mensaje SOAP usando un esquema XSD.

    :param xml_data: El XML completo del mensaje SOAP.
    :param xsd_path: La ruta al archivo XSD que define el esquema de validación.
    :raises: ValueError si el XML no cumple con el esquema XSD.
    """
    logger.info("Validando el XML contra el esquema XSD")

    # Parsear el archivo XSD
    with open(xsd_path, 'rb') as xsd_file:
        schema_root = etree.parse(xsd_file)
        schema = etree.XMLSchema(schema_root)

    # Parsear el XML
    try:
        xml_doc = etree.fromstring(xml_data)
    except etree.XMLSyntaxError as e:
        logger.error(f"Error de sintaxis en el XML: {e}")
        raise ValueError("El XML tiene un error de sintaxis.")

    # Extraer el contenido del <Body>
    body_content = xml_doc.find(".//{http://schemas.xmlsoap.org/soap/envelope/}Body/*")

    if body_content is None:
        logger.error("No se encontró el elemento Body en el XML")
        raise ValueError("No se encontró el elemento Body en el XML")

    # Validar el contenido del Body
    try:
        schema.assertValid(body_content)
        logger.info("XML válido según el esquema XSD")
    except etree.DocumentInvalid as e:
        logger.error(f"Error de validación del XML: {e}")
        for error in schema.error_log:
            logger.error(f"Línea {error.line}: {error.message}")
        raise ValueError("El XML no cumple con el esquema XSD. Ver logs para detalles.")

def obtener_factura_venta(docname):
    logger.info(f"Obteniendo la factura de venta: {docname}")
    return get_doc('Sales Invoice', docname)



def construir_xml_emitidas(facturas):
    logger.info("Construyendo el XML de las facturas emitidas")

    if not facturas:
        logger.error("No se proporcionaron facturas para construir el XML")
        return None

    # Mapa para determinar el IDType basado en custom_tipo_de_identificacion
    id_type_map = {
        "NIF": "01",
        "CIF": "01",  # La AEAT trata CIF y NIF como 01
        "NIE": "04",
        "Pasaporte": "03"
    }

    # Obtener información de la empresa de la primera factura
    empresa = facturas[0].company
    company_doc = get_doc('Company', empresa)
    nif_titular = company_doc.tax_id

    logger.info(f"NIF del titular: {nif_titular}")

    # Crear el elemento Envelope
    envelope = etree.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope", nsmap={
        "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
        "siiLR": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd",
        "sii": "https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd"
    })
    body = etree.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
    root = etree.SubElement(body, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}SuministroLRFacturasEmitidas")

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
    tipo_comunicacion.text = facturas[0].custom_tipo_comunicacion.split(":")[0].strip() if facturas[0].custom_tipo_comunicacion else "A0"

    # Crear registros para las facturas emitidas
    for factura in facturas:
        registro = etree.SubElement(root, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}RegistroLRFacturasEmitidas")

        # Periodo de liquidación
        periodo_liquidacion = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}PeriodoLiquidacion")
        ejercicio = etree.SubElement(periodo_liquidacion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Ejercicio")
        ejercicio.text = str(factura.posting_date.year)
        periodo = etree.SubElement(periodo_liquidacion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Periodo")
        periodo.text = str(factura.posting_date.month).zfill(2)

        # Información de la factura
        id_factura = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}IDFactura")
        id_emisor_factura = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}IDEmisorFactura")
        nif_emisor = etree.SubElement(id_emisor_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
        nif_emisor.text = nif_titular
        num_factura = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NumSerieFacturaEmisor")
        num_factura.text = str(factura.name)
        fecha = etree.SubElement(id_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}FechaExpedicionFacturaEmisor")
        fecha.text = factura.posting_date.strftime('%d-%m-%Y')

        # Detalles de la factura
        factura_expedida = etree.SubElement(registro, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd}FacturaExpedida")
        tipo_factura = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoFactura")
        tipo_factura_value = factura.custom_tipo_factura.split(":")[0].strip() if factura.custom_tipo_factura else "F1"
        tipo_factura.text = tipo_factura_value
        clave_regimen = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}ClaveRegimenEspecialOTrascendencia")
        clave_regimen_value = factura.custom_clave_regimen.split(":")[0].strip() if factura.custom_clave_regimen else "01"
        clave_regimen.text = clave_regimen_value
        importe_total = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}ImporteTotal")
        importe_total.text = f"{factura.grand_total:.2f}"
        descripcion_operacion = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DescripcionOperacion")
        descripcion_operacion.text = factura.custom_descripcion_factura if factura.custom_descripcion_factura else "Venta de Producto/Servicio"

        # Contraparte
        contraparte = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Contraparte")
        nombre_cliente = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NombreRazon")
        nombre_cliente.text = str(factura.customer_name)

        # Obtener el tipo de identificación y el NIF/ID del cliente desde el Doctype Customer
        cliente_doc = get_doc('Customer', factura.customer)
        tipo_identificacion = cliente_doc.custom_tipo_de_identificacion  # Obtener el campo del Doctype Customer
        nif_cliente = cliente_doc.tax_id

        # Obtener el código del país desde el Doctype "Country"
        pais_doc = get_doc('Country', cliente_doc.custom_pais)
        codigo_pais = pais_doc.code.upper()  # Capitalizar el código del país

        if tipo_identificacion in ["NIE", "Pasaporte"]:
            # Contraparte con IDOtro
            id_otros = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}IDOtro")
            codigo_pais_elem = etree.SubElement(id_otros, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CodigoPais")
            codigo_pais_elem.text = codigo_pais
            id_type = etree.SubElement(id_otros, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}IDType")
            id_type.text = id_type_map.get(tipo_identificacion, "07")  # Usar un valor predeterminado si no coincide
            id_cliente = etree.SubElement(id_otros, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}ID")
            id_cliente.text = nif_cliente
        else:
            # Para NIF y CIF, usar la estructura NIF sin desglose adicional
            nif_cliente_elem = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
            nif_cliente_elem.text = nif_cliente

        # TipoDesglose para la factura exenta o no exenta
        tipo_desglose = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoDesglose")

        if factura.taxes:
            # Si hay impuestos, agregar el bloque NoExenta
            no_exenta = etree.SubElement(tipo_desglose, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NoExenta")
            tipo_no_exenta = etree.SubElement(no_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoNoExenta")
            tipo_no_exenta_value = factura.custom_tipo_no_exenta.split(":")[0].strip() if factura.custom_tipo_no_exenta else "S1"
            tipo_no_exenta.text = tipo_no_exenta_value

            desglose_iva = etree.SubElement(no_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseIVA")
            for tax in factura.taxes:
                detalle_iva = etree.SubElement(desglose_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
                tipo_impositivo = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
                tipo_impositivo.text = str(tax.rate or 0)
                base_imponible = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
                base_imponible.text = f"{factura.total_taxes_and_charges:.2f}"
                cuota_repercutida = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaRepercutida")
                cuota_repercutida.text = f"{(tax.tax_amount or 0):.2f}"
        else:
            # Si no hay impuestos, usar el bloque Sujeta con Exenta (sin PrestacionServicios)
            desglose_tipo_operacion = etree.SubElement(tipo_desglose, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseTipoOperacion")
            prestacionservicios = etree.SubElement(desglose_tipo_operacion, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}PrestacionServicios")
            sujeta = etree.SubElement(prestacionservicios, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Sujeta")
            exenta = etree.SubElement(sujeta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Exenta")
            detalle_exenta = etree.SubElement(exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleExenta")
            causa_exencion = etree.SubElement(detalle_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CausaExencion")
            causa_exencion.text = "E1"
            base_imponible_exenta = etree.SubElement(detalle_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
            base_imponible_exenta.text = f"{factura.total:.2f}"

    logger.info("XML construido con éxito")
    return etree.tostring(envelope, pretty_print=True, xml_declaration=True, encoding='UTF-8')


def guardar_xml(xml_firmado, filename):
    logger.info(f"Guardando el XML firmado en {filename}")
    with open(filename, 'wb') as f:  # Usar 'wb' para escribir bytes
        f.write(xml_firmado)
    logger.info("XML guardado con éxito")


def enviar_xml_a_aeat(xml_firmado, p12_file_path, p12_password):
    logger.info("Enviando XML firmado a la AEAT")
    try:
        session = Session()
        session.mount('https://', Pkcs12Adapter(pkcs12_filename=p12_file_path, pkcs12_password=p12_password))
        transport = Transport(session=session)
        client = Client(wsdl=wsdl_emitidas, transport=transport)
        signed_xml_element = etree.fromstring(xml_firmado)

        namespaces = {
            'sii': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd',
            'siiLR': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroLR.xsd'
        }

        # Extracción de la cabecera
        cabecera = signed_xml_element.find('.//sii:Cabecera', namespaces=namespaces)
        if cabecera is None:
            raise ValueError("Cabecera no encontrada en el XML")

        datos_a_enviar = {
            'Cabecera': {
                'IDVersionSii': cabecera.findtext('.//sii:IDVersionSii', default='', namespaces=namespaces),
                'Titular': {
                    'NombreRazon': cabecera.findtext('.//sii:Titular/sii:NombreRazon', default='', namespaces=namespaces),
                    'NIF': cabecera.findtext('.//sii:Titular/sii:NIF', default='', namespaces=namespaces)
                },
                'TipoComunicacion': cabecera.findtext('.//sii:TipoComunicacion', default='', namespaces=namespaces)
            },
            'RegistroLRFacturasEmitidas': []
        }

        # Extracción de los registros de facturas emitidas
        registros = signed_xml_element.findall('.//siiLR:RegistroLRFacturasEmitidas', namespaces=namespaces)
        if not registros:
            raise ValueError("No se encontraron registros de facturas emitidas en el XML")

        for registro in registros:
            # Extracción de la contraparte
            contraparte_element = registro.find('.//siiLR:FacturaExpedida/sii:Contraparte', namespaces=namespaces)
            if contraparte_element is None:
                raise ValueError("Contraparte no encontrada en el registro de factura")

            contraparte = {
                'NombreRazon': contraparte_element.findtext('.//sii:NombreRazon', default='', namespaces=namespaces),
                'IDOtro': None,
                'NIF': contraparte_element.findtext('.//sii:NIF', default=None, namespaces=namespaces)
            }

            id_otro_element = contraparte_element.find('.//sii:IDOtro', namespaces=namespaces)
            if id_otro_element is not None:
                contraparte['IDOtro'] = {
                    'CodigoPais': id_otro_element.findtext('.//sii:CodigoPais', default='', namespaces=namespaces),
                    'IDType': id_otro_element.findtext('.//sii:IDType', default='', namespaces=namespaces),
                    'ID': id_otro_element.findtext('.//sii:ID', default='', namespaces=namespaces)
                }
                tipo_desglose_key = 'DesgloseTipoOperacion'
            else:
                tipo_desglose_key = 'DesgloseFactura'

            # Preparar los detalles del desglose según el tipo de operación
            desglose_element = registro.find(f'.//siiLR:FacturaExpedida/sii:TipoDesglose/sii:{tipo_desglose_key}', namespaces=namespaces)
            if desglose_element is None:
                if tipo_desglose_key == 'DesgloseFactura':
                    tipo_desglose_key = 'DesgloseTipoOperacion'
                    desglose_element = registro.find(f'.//siiLR:FacturaExpedida/sii:TipoDesglose/sii:{tipo_desglose_key}', namespaces=namespaces)
                if desglose_element is None:
                    raise ValueError(f"No se encontró el elemento {tipo_desglose_key} en el registro de factura")

            desglose = {}

            prestacion_servicios_element = desglose_element.find('.//sii:PrestacionServicios', namespaces=namespaces)
            if prestacion_servicios_element is not None:
                sujeta_element = prestacion_servicios_element.find('.//sii:Sujeta', namespaces=namespaces)
                if sujeta_element is not None:
                    exenta_element = sujeta_element.find('.//sii:Exenta', namespaces=namespaces)
                    if exenta_element is not None:
                        detalle_exenta_element = exenta_element.find('.//sii:DetalleExenta', namespaces=namespaces)
                        if detalle_exenta_element is not None:
                            desglose['PrestacionServicios'] = {
                                'Sujeta': {
                                    'Exenta': {
                                        'DetalleExenta': {
                                            'CausaExencion': detalle_exenta_element.findtext('.//sii:CausaExencion', default='', namespaces=namespaces),
                                            'BaseImponible': detalle_exenta_element.findtext('.//sii:BaseImponible', default='0.00', namespaces=namespaces)
                                        }
                                    }
                                }
                            }

            # Asegurarse de que el desglose incluya la información correcta para facturas exentas
            if not desglose:
                desglose['Sujeta'] = {
                    'Exenta': {
                        'DetalleExenta': {
                            'CausaExencion': '',
                            'BaseImponible': '0.00'
                        }
                    }
                }

            desglose_factura = {'DesgloseFactura': desglose} if tipo_desglose_key == 'DesgloseFactura' else {'DesgloseTipoOperacion': desglose}

            # Construcción del registro a enviar
            registro_a_enviar = {
                'PeriodoLiquidacion': {
                    'Ejercicio': registro.findtext('.//sii:PeriodoLiquidacion/sii:Ejercicio', default='', namespaces=namespaces),
                    'Periodo': registro.findtext('.//sii:PeriodoLiquidacion/sii:Periodo', default='', namespaces=namespaces)
                },
                'IDFactura': {
                    'IDEmisorFactura': {
                        'NIF': registro.findtext('.//siiLR:IDFactura/sii:IDEmisorFactura/sii:NIF', default='', namespaces=namespaces)
                    },
                    'NumSerieFacturaEmisor': registro.findtext('.//siiLR:IDFactura/sii:NumSerieFacturaEmisor', default='', namespaces=namespaces),
                    'FechaExpedicionFacturaEmisor': registro.findtext('.//siiLR:IDFactura/sii:FechaExpedicionFacturaEmisor', default='', namespaces=namespaces)
                },
                'FacturaExpedida': {
                    'TipoFactura': registro.findtext('.//siiLR:FacturaExpedida/sii:TipoFactura', default='', namespaces=namespaces),
                    'ClaveRegimenEspecialOTrascendencia': registro.findtext('.//siiLR:FacturaExpedida/sii:ClaveRegimenEspecialOTrascendencia', default='', namespaces=namespaces),
                    'ImporteTotal': registro.findtext('.//siiLR:FacturaExpedida/sii:ImporteTotal', default='', namespaces=namespaces),
                    'DescripcionOperacion': registro.findtext('.//siiLR:FacturaExpedida/sii:DescripcionOperacion', default='', namespaces=namespaces),
                    'Contraparte': contraparte,
                    'TipoDesglose': desglose_factura
                }
            }

            datos_a_enviar['RegistroLRFacturasEmitidas'].append(registro_a_enviar)

        # Limpiar los campos vacíos de la contraparte
        for registro in datos_a_enviar['RegistroLRFacturasEmitidas']:
            contraparte = registro['FacturaExpedida']['Contraparte']
            if contraparte['NIF'] is None:
                del contraparte['NIF']
            if contraparte['IDOtro'] is None:
                del contraparte['IDOtro']

        logger.debug(f"Datos a enviar: {datos_a_enviar}")
        respuesta = client.service.SuministroLRFacturasEmitidas(**datos_a_enviar)
        logger.info("XML enviado con éxito")
        logger.info(f"Respuesta de la AEAT: {respuesta}")

        return respuesta, datos_a_enviar

    except Exception as e:
        logger.error(f"Error al enviar el XML a la AEAT: {e}")
        raise



def enviar_facturas_emitidas(docnames):
    logger.info("Iniciando el proceso de envío de facturas emitidas")
    
    # Asegurarse de que docnames sea una lista
    if isinstance(docnames, str):
        # Si se recibe una cadena, quita los corchetes y descompónla en una lista
        docnames = docnames.strip("[]").replace('"', '').replace("'", "").split(",")
    
    # Obtener cada factura basada en el nombre de documento
    facturas = []
    for docname in docnames:
        docname = docname.strip()  # Elimina espacios en blanco al inicio y al final
        factura = get_doc('Sales Invoice', docname)
        if factura:
            facturas.append(factura)
        else:
            logger.error(f"Factura de Venta [{docname}] no encontrada")
            return {"error": f"Factura de Venta [{docname}] no encontrada"}  # Salir si una factura no se encuentra
    
    xml_data = construir_xml_emitidas(facturas)

    xsd_path = '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/WSDL/SuministroLR.xsd'
    guardar_xml(xml_data, '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/xml_emitidas.xml')

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
    
    logger.info("Proceso de envío de facturas emitidas finalizado")
