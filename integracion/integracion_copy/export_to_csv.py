import frappe
import csv
import os

def export_web_form_data():
    # Ruta del archivo CSV de salida
    output_file = '/home/frappe/frappe-bench/sql_backup/web_form.csv'

    # Consulta SQL
    query = "SELECT * FROM `tabFormularios Web Comerciales`"
    data = frappe.db.sql(query, as_dict=True)

    # Obtener los nombres de las columnas
    if data:
        columns = data[0].keys()

        # Escribir los datos en un archivo CSV
        with open(output_file, 'w', newline='') as csvfile:
            csvwriter = csv.DictWriter(csvfile, fieldnames=columns)
            csvwriter.writeheader()  # Escribir los encabezados de las columnas
            csvwriter.writerows(data)  # Escribir los datos
        
        frappe.logger().info(f"Datos exportados exitosamente a {output_file}")
    else:
        frappe.logger().warning("No se encontraron datos para exportar")
