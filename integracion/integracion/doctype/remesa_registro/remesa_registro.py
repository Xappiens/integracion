# Copyright (c) 2024, Xappiens and contributors
# For license information, please see license.txt

import frappe

import json
from frappe.model.document import Document
from integracion.integracion.generate_c34_compra import get_supplier_iban, create_payment_entry_for_purchase_invoice

import logging

# Configurar el logger
logger = logging.getLogger(__name__)

handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/remesa.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


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

    @frappe.whitelist()
    def cargar_campos_factura_pago(self, date, bank_account=None):
        # TODO Agregar lógica para remesas pagadas parcialmente

        # Buscar pagos que tengan la remesa(self) asignada
        purchase_invoices = frappe.db.get_all(
            "Purchase Invoice",
            filters={
                "custom_remesa": self.name,
                "custom_remesa_emitida": 1,
                "docstatus": ['in', [0, 1]]
            }
        )
        banco = frappe.get_doc("Bank Account", bank_account)
        company_bank_account = banco.account if banco else None

        # Vaciar antes de proceder
        # TODO Lógica para no tener que remover las líneas
        self.facturas = []
        self.save()
        mensajes = []

        for purchase_invoice in purchase_invoices:
            purchase_invoice_doc = frappe.get_doc("Purchase Invoice", purchase_invoice.name)

            # Buscar líneas de pago con la Factura de Compra (Purchase Invoice) asignada
            payment_names = frappe.db.get_all(
                "Payment Entry Reference",
                filters={
                    "reference_doctype": "Purchase Invoice",
                    "reference_name": purchase_invoice.name,
                    "docstatus": ['in', [0, 1]]
                },
                fields=["parent"]
            )
            payment_entry_doc = None

            if len(payment_names):
                for payment_name in payment_names:
                    payment_entry = frappe.get_doc("Payment Entry", payment_name.get("parent"))

                    if payment_entry.docstatus == 1:
                        # Comprobar si la fecha del pago coincide con la fecha proporcionada
                        if payment_entry.posting_date != date:
                            # Cancelar el pago existente
                            payment_entry.cancel()
                            
                            # Crear nuevo pago basado en el anterior
                            new_payment_entry = frappe.copy_doc(payment_entry)
                            new_payment_entry.docstatus = 0  # Borrador
                            new_payment_entry.amended_from = payment_entry.name
                            new_payment_entry.posting_date = date
                            new_payment_entry.bank_account = bank_account
                            if company_bank_account:
                                new_payment_entry.paid_from = company_bank_account or ""
                                new_payment_entry.paid_from_account_currency = frappe.get_value(
                                    "Account", company_bank_account, "account_currency"
                                ) if company_bank_account else "EUR"

                            new_payment_entry.insert()
                            new_payment_entry.submit()
                            payment_entry_doc = new_payment_entry
                        else:
                            payment_entry_doc = payment_entry

                        break
                    elif (
                        payment_entry.docstatus == 0 and
                        round(payment_entry.paid_amount, 2) == round(purchase_invoice_doc.outstanding_amount, 2)
                    ):
                        payment_entry_doc = payment_entry

                        # Usar la cuenta bancaria especificada
                        payment_entry_doc.paid_from = company_bank_account or ""
                        payment_entry_doc.paid_from_account_currency = frappe.get_value(
                            "Account", company_bank_account, "account_currency"
                        ) if company_bank_account else None
                        payment_entry_doc.bank_account = bank_account
                        payment_entry_doc.posting_date = date
                        payment_entry_doc.save()
                        payment_entry_doc.submit()
                        frappe.db.commit()

                        break

            else:
                # La factura no tiene pagos y está marcada como pagada
                if purchase_invoice_doc.is_paid:
                    # Cancelar factura original y la corrige
                    # (amend; Reemplaza la factura original con la nueva corregida)
                    purchase_invoice_doc.cancel()
                    amended_pinv = frappe.copy_doc(purchase_invoice_doc)
                    amended_pinv.amended_from = purchase_invoice_doc

                    # Cambiar estado de pagado a no pagado, quitando los términos de pago, la cantidad pendiente
                    # y el estado de pagado
                    amended_pinv.payment_schedule = []
                    amended_pinv.outstanding_amount = 0
                    amended_pinv.is_paid = 0

                    # cambiar a fecha de la herramienta
                    amended_pinv.set_posting_time = 1
                    amended_pinv.posting_date = date
                    amended_pinv.due_date = date
                    if not amended_pinv.bill_date:
                        amended_pinv.bill_date = date
                    
                    if not amended_pinv.bill_no:
                        amended_pinv.bill_no = amended_pinv.name

                    amended_pinv.insert(ignore_permissions=True)
                    purchase_invoice_doc = amended_pinv
                    purchase_invoice_doc.submit()

                    frappe.db.commit()

                # Conseguir banco e IBAN del proveedor de la Factura de Compra para crear pago
                supplier_bank = get_supplier_iban(purchase_invoice_doc.supplier, purchase_invoice_doc.company)
                supplier_iban = supplier_bank.get('iban') if supplier_bank else None

                # Crear pago (Payment Entry) como lo hace la generación de remesas
                payment_entry = create_payment_entry_for_purchase_invoice(purchase_invoice_doc, supplier_iban, company_bank_account)

                if payment_entry:
                    payment_entry_doc = frappe.get_doc("Payment Entry", payment_entry)
                    # Actualizar la cuenta bancaria del pago recién creado
                    payment_entry_doc.paid_from = company_bank_account or ""
                    payment_entry_doc.paid_from_account_currency = frappe.get_value(
                        "Account", company_bank_account, "account_currency"
                    ) if company_bank_account else None
                    payment_entry_doc.save()
                    payment_entry_doc.submit()
                    frappe.db.commit()

            mensajes.append(f"Payment Entry created for {purchase_invoice_doc.name}")

            # Finalmente, Actualizar líneas de la remesa
            self.append("facturas", {
                "factura": purchase_invoice_doc.name,
                "pago": payment_entry_doc.name if payment_entry_doc else None,
                "importe": payment_entry_doc.paid_amount if payment_entry_doc else purchase_invoice_doc.grand_total
            })

        frappe.log_error(message=mensajes, title="Remesa Registro")
        self.set_total_importe()
        self.save()
        frappe.db.commit()

    @frappe.whitelist()
    def calcular_totales(names):
        for remesa in json.loads(names):
            remesa_doc = frappe.get_doc("Remesa Registro", remesa)

            remesa_doc.set_total_importe()
