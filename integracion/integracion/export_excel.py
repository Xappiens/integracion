import frappe
import os
import csv

def export_expense_claim_summary():
    try:
        # Obtener datos de Expense Claim
        expense_claim_details = frappe.db.sql("""
            SELECT
                ec.employee,
                ec_detail.expense_type AS expense_claim_type,
                ec_detail.amount AS total_claimed_amount
            FROM
                `tabExpense Claim Detail` ec_detail
            INNER JOIN
                `tabExpense Claim` ec
            ON
                ec_detail.parent = ec.name
            WHERE
                ec.docstatus = 0
        """, as_dict=True)

        if not expense_claim_details:
            frappe.throw("No se encontraron registros de Expense Claim en borrador.")

        # Obtener datos de empleados
        employees = frappe.db.get_all(
            'Employee',
            fields=['name as employee', 'employee_name', 'custom_dninie_Id as dni', 'company']
        )

        if not employees:
            frappe.throw("No se encontraron registros de empleados.")

        # Crear diccionarios para unir datos
        employees_map = {emp['employee']: emp for emp in employees}

        # Procesar datos combinados
        processed_data = []
        for claim in expense_claim_details:
            employee_data = employees_map.get(claim['employee'])
            if employee_data:
                processed_data.append({
                    'dni': employee_data['dni'],
                    'employee_name': employee_data['employee_name'],
                    'company': employee_data['company'],
                    'expense_claim_type': claim['expense_claim_type'],
                    'total_claimed_amount': claim['total_claimed_amount']
                })

        if not processed_data:
            frappe.throw("No se pudieron procesar los datos de Expense Claim.")

        # Agrupar y sumar por empleado, empresa y tipo de gasto
        aggregated_data = {}
        for record in processed_data:
            key = (record['dni'], record['employee_name'], record['company'], record['expense_claim_type'])
            if key not in aggregated_data:
                aggregated_data[key] = 0
            aggregated_data[key] += record['total_claimed_amount']

        # Crear CSV con los datos agrupados
        file_name = "Expense_Claim_Summary_Grouped.csv"
        script_directory = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_directory, file_name)

        with open(file_path, mode='w', newline='', encoding='utf-8') as csv_file:
            fieldnames = ['dni', 'employee_name', 'company', 'expense_claim_type', 'total_claimed_amount']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            for (dni, employee_name, company, expense_claim_type), total_claimed_amount in aggregated_data.items():
                writer.writerow({
                    'dni': dni,
                    'employee_name': employee_name,
                    'company': company,
                    'expense_claim_type': expense_claim_type,
                    'total_claimed_amount': round(total_claimed_amount, 2)  # Redondear para evitar decimales extraños
                })

        frappe.msgprint(f"Archivo CSV generado correctamente: {file_path}")
    except Exception as e:
        frappe.throw(f"Error en export_expense_claim_summary: {str(e)}")

# Llamar a la función
export_expense_claim_summary()
