'''
import frappe

def log_custom_fields_with_old_contract_code():
    # Define el nombre del Doctype que queremos procesar
    doctype_name = "Job Offer"
    
    # Mapeo de `custom_tipo_de_contrato` a códigos antiguos (`custom_tipo_de_contrato_old`)
    contract_code_mapping = {
        "Indefinido": "001",  # Ejemplo: código 001 para contrato indefinido
        "Temporal": "002",    # Ejemplo: código 002 para contrato temporal
        "Formación": "003",   # Ejemplo: código 003 para contrato de formación
        # Añade más mapeos si es necesario
    }

    # Recupera todas las instancias del Doctype donde `custom_tipo_de_contrato` no está vacío
    instances = frappe.get_all(
        doctype_name,
        filters={"custom_tipo_de_contrato": ["!=", ""]},  # Filtra registros donde `custom_tipo_de_contrato` no esté vacío
        fields=["name", "custom_tipo_de_contrato", "custom_discapacidad"]
    )

    # Construye un mensaje consolidado para el log
    log_message = "Detalles de las instancias procesadas:\n\n"
    for instance in instances:
        # Determina el código para `custom_tipo_de_contrato_old`
        contract_code_old = contract_code_mapping.get(instance["custom_tipo_de_contrato"], "N/A")
        
        # Agrega los detalles de la instancia al mensaje del log
        log_message += (
            f"- Nombre: {instance['name']}\n"
            f"  Tipo de Contrato: {instance['custom_tipo_de_contrato']}\n"
            f"  Discapacidad: {instance['custom_discapacidad']}\n"
            f"  Código Tipo de Contrato (OLD): {contract_code_old}\n\n"
        )

    # Crea una única entrada en `Error Log`
    log_entry = frappe.get_doc({
        "doctype": "Error Log",
        "method": "log_custom_fields_with_old_contract_code",  # Título o método que generó el log
        "error": log_message  # Mensaje consolidado
    })
    log_entry.insert(ignore_permissions=True)  # Inserta el log

    # Confirma la operación
    frappe.db.commit()
    print(f"Se ha registrado un log consolidado para {len(instances)} instancias de {doctype_name} con 'custom_tipo_de_contrato' no vacío.")
'''
import frappe

def log_custom_fields_with_old_contract_code():
    # Define el nombre del Doctype que queremos procesar
    doctype_name = "Job Offer"
    
    # Recupera todas las instancias del Doctype donde `custom_tipo_de_contrato_old` no está vacío
    instances = frappe.get_all(
        doctype_name,
        filters={"custom_tipo_de_contrato_old": ["!=", ""]},  # Filtra registros donde `custom_tipo_de_contrato_old` no esté vacío
        fields=["name", "custom_tipo_de_contrato", "custom_tipo_de_contrato_old", "custom_discapacidad"]
    )

    # Construye un mensaje consolidado para el log
    log_message = "Detalles de las instancias procesadas:\n\n"
    for instance in instances:
        # Agrega los detalles de la instancia al mensaje del log
        log_message += (
            f"- Nombre: {instance['name']}\n"
            f"  Tipo de Contrato: {instance['custom_tipo_de_contrato']}\n"
            f"  Tipo de Contrato (Old): {instance['custom_tipo_de_contrato_old']}\n"
            f"  Discapacidad: {instance['custom_discapacidad']}\n\n"
        )

    # Crea una única entrada en `Error Log`
    log_entry = frappe.get_doc({
        "doctype": "Error Log",
        "method": "log_custom_fields_with_old_contract_code",  # Título o método que generó el log
        "error": log_message  # Mensaje consolidado
    })
    log_entry.insert(ignore_permissions=True)  # Inserta el log

    # Confirma la operación
    frappe.db.commit()
    print(f"Se ha registrado un log consolidado para {len(instances)} instancias de {doctype_name} con 'custom_tipo_de_contrato_old' no vacío.")
