# Copyright (c) 2024, Xappiens and contributors
# For license information, please see license.txt

import frappe

import json
from frappe.model.document import Document
from integracion.integracion.generate_c34_compra import get_supplier_iban, create_payment_entry_for_purchase_invoice

# import logging

# # Configurar el logger
# logger = logging.getLogger(__name__)

# handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/remesa.log')
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)
# logger.setLevel(logging.DEBUG)


class RemesaRegistro(Document):

    def on_update(self):
        self.set_total_importe()

    @frappe.whitelist()
    def set_total_importe(self):
        total = 0

        for factura in self.facturas:
            total += factura.importe

        self.db_set("custom_total", total)

    @frappe.whitelist()
    def eliminar_conciliacion(self):
        for factura in self.facturas:
            # TODO Implementar más documentos
            pago = factura.pago
            payment_document = "Payment Entry" if pago else "Purchase Invoice"
            payment_entry = pago if pago else factura.factura
            bank_transaction = frappe.db.get_value(
                "Bank Transaction Payments",
                {"payment_document": payment_document, "payment_entry": payment_entry},
                "parent"
            )

            if bank_transaction:
                frappe.db.delete(
                    "Bank Transaction Payments", {"payment_document": payment_document, "payment_entry": payment_entry}
                )
                frappe.db.commit()

                bank_transaction_doc = frappe.get_doc("Bank Transaction", bank_transaction)
                bank_transaction_doc.save()
                bank_transaction_doc.validate_duplicate_references()
                bank_transaction_doc.allocate_payment_entries()
                bank_transaction_doc.update_allocated_amount()
                bank_transaction_doc.set_status()

                self.db_set("custom_total_localizado", 0)


            # bank_transaction_doc = bank_transaction
            # transaction_line_doc = frappe.get_doc("Bank Transaction Payments", transaction_line)

    @frappe.whitelist()
    def cargar_campos_factura_pago(self):
        # TODO Agregar lógica para remesas pagadas parcialmente
        purchase_invoices = frappe.db.get_all(
            "Purchase Invoice",
            filters={
                "custom_remesa": self.name,
                "custom_remesa_emitida": 1,
                "docstatus": ['in', [0, 1]]
            }
        )

        self.facturas = []
        self.save()
        mensajes = []
        for purchase_invoice in purchase_invoices:
            purchase_invoice_doc = frappe.get_doc("Purchase Invoice", purchase_invoice.name)
            payment_entry = frappe.db.get_value(
                "Payment Entry Reference",
                {"reference_doctype": "Purchase Invoice", "reference_name": purchase_invoice.name, "docstatus": 1},
                "parent"
            )
            payment_entry_doc = None

            if payment_entry:
                payment_entry_doc = frappe.get_doc("Payment Entry", payment_entry)
            else:
                supplier_bank = get_supplier_iban(purchase_invoice.supplier, purchase_invoice.company)
                supplier_iban = supplier_bank.get('iban') if supplier_bank else None

                payment_entry = create_payment_entry_for_purchase_invoice(purchase_invoice_doc, supplier_iban)

                if payment_entry:
                    payment_entry_doc = frappe.get_doc("Payment Entry", payment_entry)
            mensajes.append(f"Payment Entry created for {purchase_invoice_doc.name}")
            self.append("facturas", {
                "factura": purchase_invoice_doc.name,
                "pago": payment_entry_doc.name if payment_entry_doc else None,
                "importe": payment_entry_doc.paid_amount if payment_entry_doc else purchase_invoice_doc.grand_total
            })
        frappe.log_error(message=mensajes, title="Remesa Registro")
        self.save()
        frappe.db.commit()

@frappe.whitelist()
def calcular_totales(names):
    for remesa in json.loads(names):
        remesa_doc = frappe.get_doc("Remesa Registro", remesa)

        remesa_doc.set_total_importe()
