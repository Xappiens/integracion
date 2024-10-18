# Copyright (c) 2024, Xappiens and contributors
# For license information, please see license.txt

import frappe
from frappe import _

def execute(filters: dict | None = None):
	columns, data = get_columns(), []

	if not filters:
		return columns, data

    # Diccionario con los valores de los filtros para facturas intracomunitarias
	filters_dict = {
        "company": filters.get("company"),
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

	conditions = [
		"inv.company = %(company)s",
		"inv.posting_date >= %(from_date)s",
		"inv.posting_date <= %(to_date)s",
		# Solo facturas intracomunitarias
		"inv.custom_intracomunitaria = 1",
		# Solo incluir facturas validadas
		"inv.docstatus = 1",
	]

	query = f"""
        SELECT
            sup.supplier_name AS supplier,
            sup.tax_id AS cif,
            sup.custom_cp AS codigo_postal,
			SUM(ABS(pii.base_net_amount)) AS total_base,
			SUM(
				CASE
					WHEN tax.account_head LIKE '472%%' THEN ABS(tax.tax_amount)
					ELSE 0
				END
			) AS total_soportadas,
			SUM(
				CASE
					WHEN tax.account_head LIKE '477%%' THEN ABS(tax.tax_amount)
					ELSE 0
				END
			) AS total_repercutidas
        FROM
            `tabPurchase Invoice` AS inv
        LEFT JOIN 
            `tabPurchase Invoice Item` AS pii ON inv.name = pii.parent
        LEFT JOIN
            `tabSupplier` AS sup ON inv.supplier = sup.name
		LEFT JOIN
			`tabPurchase Taxes and Charges` AS tax ON tax.parent = inv.name
        WHERE
            {" AND ".join(conditions)}
        GROUP BY
            sup.supplier_name, sup.tax_id, sup.custom_cp
        ORDER BY 
            sup.supplier_name
    """

	data = frappe.db.sql(query, filters_dict, as_dict=True)

	return columns, data

def get_columns():
	return [
		{"label": _("Supplier"), "fieldtype": "Link", "fieldname": "supplier", "options": "Supplier", "width": 200,},
		{"label": _("Cif"), "fieldtype": "Data", "fieldname": "cif", "width": 120,},
		{"label": _("Postal Code"), "fieldname": "codigo_postal", "fieldtype": "Data", "width": 100},
		{"label": _("Total"), "fieldtype": "Currency", "fieldname": "total_base", "width": 120,},
		{"label": _("Total Soportado"), "fieldtype": "Currency", "fieldname": "total_soportadas", "width": 120,},
		{"label": _("Total Repercutido"), "fieldtype": "Currency", "fieldname": "total_repercutidas", "width": 120,},
	]