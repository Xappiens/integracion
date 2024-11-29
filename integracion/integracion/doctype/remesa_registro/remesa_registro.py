# Copyright (c) 2024, Xappiens and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class RemesaRegistro(Document):
	def after_insert(self):
		self.set_total_importe()

	@frappe.whitelist()
	def set_total_importe(self):
		total = 0

		for factura in self.facturas:
			total += factura.importe

		self.db_set("custom_total", total)