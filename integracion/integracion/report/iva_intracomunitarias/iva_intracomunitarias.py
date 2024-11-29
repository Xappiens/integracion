# Copyright (c) 2024, Xappiens and contributors
# For license information, please see license.txt

import frappe
from frappe import _

# import logging

# # Configurar el logger
# logger = logging.getLogger(__name__)
# handler = logging.FileHandler(
# 	'/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/iva_intracomunitarias.log'
# )
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)
# logger.setLevel(logging.INFO)

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

	query_bases = f"""
        SELECT
            sup.supplier_name AS supplier,
            sup.tax_id AS cif,
			SUM(ABS(pii.base_net_amount)) AS total_base
        FROM
            `tabPurchase Invoice` AS inv
        LEFT JOIN
            `tabPurchase Invoice Item` AS pii ON inv.name = pii.parent
        LEFT JOIN
            `tabSupplier` AS sup ON inv.supplier = sup.name
        WHERE
            {" AND ".join(conditions)}
        GROUP BY
            sup.supplier_name, sup.tax_id
        ORDER BY
            sup.supplier_name
    """

	bases = frappe.db.sql(query_bases, filters_dict, as_dict=True)

	query_retenciones = f"""
        SELECT
            sup.supplier_name AS supplier, sup.tax_id AS cif,
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
            `tabSupplier` AS sup ON inv.supplier = sup.name
		LEFT JOIN
			`tabPurchase Taxes and Charges` AS tax ON tax.parent = inv.name
        WHERE
            {" AND ".join(conditions)}
        GROUP BY
            sup.supplier_name, sup.tax_id
        ORDER BY
            sup.supplier_name
    """

	retenciones = frappe.db.sql(query_retenciones, filters_dict, as_dict=True)

	for entry in bases:
		entry_retenciones = list(filter(
			lambda r: r["supplier"] == entry["supplier"] and r["cif"] == entry["cif"], retenciones
		))

		if len(entry_retenciones):
			entry.update({
				"total_soportadas": entry_retenciones[0]["total_soportadas"],
				"total_repercutidas": entry_retenciones[0]["total_repercutidas"]
			})

	return columns, bases

def get_columns():
	return [
		{"label": _("Supplier"), "fieldtype": "Link", "fieldname": "supplier", "options": "Supplier", "width": 200},
		{"label": _("Cif"), "fieldtype": "Data", "fieldname": "cif", "width": 200},
		{"label": _("Total Base"), "fieldtype": "Currency", "fieldname": "total_base", "width": 100},
		{"label": _("Total Soportado"), "fieldtype": "Currency", "fieldname": "total_soportadas", "width": 100},
		{"label": _("Total Repercutido"), "fieldtype": "Currency", "fieldname": "total_repercutidas", "width": 100},
	]