import frappe
from frappe.model.mapper import get_mapped_doc
import PyPDF2
import pandas as pd
import re
from pdfreader import SimplePDFViewer, PageDoesNotExist


def extract_text_from_pdf(pdf_path):
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfFileReader(file)
        text = ""
        for page_num in range(reader.numPages):
            page = reader.getPage(page_num)
            text += page.extract_text()
        return text

@frappe.whitelist()
def prueba():	
    file_path = "/home/frappe/frappe-bench/ATUAVILA.pdf"
    pdf_text = extract_text_from_pdf(file_path)

	
	# Patrón regex para extraer los campos relevantes
    pattern = re.compile(
		r'(?P<name>[A-Z\s]+)\s+(?P<sit>ALTA|BAJA)\s+(?P<real_alt>\d{2}-\d{2}-\d{4})\s+(?P<efec_alt>\d{2}-\d{2}-\d{4})\s+(?P<real_sit>\d{2}-\d{2}-\d{4})?\s*(?P<efec_sit>\d{2}-\d{2}-\d{4})?\s+\d{2}\s+(?P<tc>\d+)\s+'
	)

	# Extraer datos usando el patrón regex
    matches = pattern.findall(pdf_text)

	# Verifica que se encontraron coincidencias
    if not matches:
        print("No se encontraron coincidencias. Verifica que el patrón regex coincida con el formato del texto extraído.")
    else:
        print(f"Se encontraron {len(matches)} coincidencias.")

	# Crear un DataFrame con los datos extraídos
    columns = ["Nombre", "Situación", "Fecha Real Alta", "Fecha Efectiva Alta", "Fecha Real Situación", "Fecha Efectiva Situación", "TC"]
    data = []

    for match in matches:
        name, sit, real_alt, efec_alt, real_sit, efec_sit, tc = match
        data.append([name.strip(), sit, real_alt, efec_alt, real_sit, efec_sit, tc])

    df = pd.DataFrame(data, columns=columns)

	# Filtrar las columnas relevantes
    filtered_df = df[["Nombre", "Situación", "Fecha Efectiva Alta", "Fecha Efectiva Situación", "TC"]]

	# Mostrar los datos extraídos por consola en modo tabla
    print("Datos filtrados:")
    print(filtered_df.to_string(index=False))

@frappe.whitelist()
def make_alumno(source_name, target_doc=None, ignore_permissions=False):		
    student = get_mapped_doc(
		"Lead",
		source_name,
		{
			"Lead": {
				"doctype": "Student",
				"field_map": {
					"fiddrst_name": "lead_name",
					"email_id":"student_email_id",
					 "mobile_no":"student_mobile_number",
                    "custom_fecha_de_nacimiento":"date_of_birth",
                    "gender":"gender",
				},
				"field_no_map": ["disabled"],
            
			}
		},
		target_doc,
		None,
		ignore_permissions=ignore_permissions,
	)
        
    return student
