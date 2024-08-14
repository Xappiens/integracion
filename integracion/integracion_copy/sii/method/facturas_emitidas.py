from zeep import Client
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
logger.setLevel(logging.INFO)

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

        # Periodo de liquidación (en lugar de PeriodoImpositivo)
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
        nif_cliente = etree.SubElement(contraparte, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NIF")
        nif_cliente.text = str(factura.tax_id)

        # Desglose del IVA
        tipo_desglose = etree.SubElement(factura_expedida, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoDesglose")
        desglose_factura = etree.SubElement(tipo_desglose, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseFactura")
        sujeta = etree.SubElement(desglose_factura, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Sujeta")

        # Si hay impuestos, agregar el bloque NoExenta
        if factura.taxes:
            no_exenta = etree.SubElement(sujeta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}NoExenta")
            tipo_no_exenta = etree.SubElement(no_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoNoExenta")
            tipo_no_exenta_value = factura.custom_tipo_no_exenta.split(":")[0].strip() if factura.custom_tipo_no_exenta else "S1"
            tipo_no_exenta.text = tipo_no_exenta_value

            desglose_iva = etree.SubElement(no_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DesgloseIVA")
            for tax in factura.taxes:
                detalle_iva = etree.SubElement(desglose_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleIVA")
                tipo_impositivo = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}TipoImpositivo")
                tipo_impositivo.text = str(tax.rate or 0)
                base_imponible = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
                base_imponible.text = f"{factura.total:.2f}"  # Cambiado a usar factura.total como base imponible
                cuota_repercutida = etree.SubElement(detalle_iva, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CuotaRepercutida")
                cuota_repercutida.text = f"{(tax.tax_amount or 0):.2f}"
        else:
            # Si no hay impuestos, agregar el bloque Exenta
            exenta = etree.SubElement(sujeta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}Exenta")
            detalle_exenta = etree.SubElement(exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}DetalleExenta")
            causa_exencion = etree.SubElement(detalle_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}CausaExencion")
            causa_exencion.text = "E1"  # Código para indicar que está exenta por una razón específica
            base_exenta = etree.SubElement(detalle_exenta, "{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroInformacion.xsd}BaseImponible")
            base_exenta.text = f"{factura.total:.2f}"  # Usar el total de la factura como base exenta


    logger.info("XML construido con éxito")
    return etree.tostring(envelope, pretty_print=True, xml_declaration=True, encoding='UTF-8')


def guardar_xml(xml_firmado, filename):
    logger.info(f"Guardando el XML firmado en {filename}")
    with open(filename, 'wb') as f:  # Usar 'wb' para escribir bytes
        f.write(xml_firmado)
    logger.info("XML guardado con éxito")

def enviar_facturas_emitidas(docnames):
    logger.info("Iniciando el proceso de envío de facturas emitidas")
    if isinstance(docnames, str):
        docnames = [docnames]
    
    facturas = [obtener_factura_venta(docname) for docname in docnames]
    xml_data = construir_xml_emitidas(facturas)

    xsd_path = '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/sii/WSDL/SuministroLR.xsd'

    # Validar el XML generado con el XSD
    try:
        validate_xml(xml_data, xsd_path)
    except Exception as e:
        logger.error(f"Error en la validación del XML: {e}")
        return

    # Obtener la empresa de la primera factura
    empresa = facturas[0].company
    logger.info(f"Empresa detectada: {empresa}")
    now = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    
    # Obtener el certificado correspondiente a la empresa
    certificado_info = certificados.get(empresa)
    if not certificado_info:
        logger.error(f"No se encontró un certificado para la empresa {empresa}")
        raise ValueError(f"No se encontró un certificado para la empresa {empresa}")
    
    p12_file_path = certificado_info['ruta']
    p12_password = certificado_info['password']
    
    # Cargar el certificado
    private_key, certificate = load_certificate(p12_file_path, p12_password)
    
    # Firmar el XML
    xml_firmado = sign_xml(xml_data.decode('utf-8'), private_key, certificate)
    
    # Guardar el XML firmado
    current_directory = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(current_directory, f'facturas_emitidas_firmadas_{empresa}_{now}.xml')
    guardar_xml(xml_firmado, output_file)
    
    logger.info("Proceso de envío de facturas emitidas finalizado")
    return output_file
