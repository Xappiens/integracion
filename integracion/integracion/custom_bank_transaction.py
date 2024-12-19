import frappe
import json

from frappe.query_builder.custom import ConstantColumn
from erpnext.accounts.doctype.bank_transaction.bank_transaction import BankTransaction, get_doctypes_for_bank_reconciliation
from erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool import get_matching_queries, reconcile_vouchers
from erpnext.accounts.utils import get_account_currency

import logging
# Configurar el logger
logger = logging.getLogger(__name__)

handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/bank_transaction.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


class CustomBankTransaction(BankTransaction):
    pass

@frappe.whitelist()
def custom_get_doctypes_for_bank_reconciliation():
    # Función a hacer override
    bank_reconciliation_doctypes = get_doctypes_for_bank_reconciliation()

    # Agregar check remesa registro
    bank_reconciliation_doctypes.extend(["Remesa Registro", "Es mismo banco"])

    return bank_reconciliation_doctypes

def custom_get_matching_queries(
	bank_account,
	company,
	transaction,
	document_types,
	exact_match,
	account_from_to=None,
	from_date=None,
	to_date=None,
	filter_by_reference_date=None,
	from_reference_date=None,
	to_reference_date=None,
	common_filters=None,
):
	currency = get_account_currency(bank_account)

	queries = get_matching_queries(
		bank_account=bank_account,
		company=company,
		transaction=transaction,
		document_types=document_types,
		exact_match=exact_match,
		account_from_to=account_from_to,
		from_date=from_date,
		to_date=to_date,
		filter_by_reference_date=filter_by_reference_date,
		from_reference_date=from_reference_date,
		to_reference_date=to_reference_date,
		common_filters=common_filters,
	)

	if "remesa_registro" in document_types:
		query = get_pi_remesas_query(exact_match, currency, common_filters)

		queries.append(query)

	return queries

def get_pi_remesas_query(exact_match, currency, common_filters):
	# get matching purchase invoice query when they are also used as payment entries (is_paid)
	remesa_registro = frappe.qb.DocType("Remesa Registro")

	amount_equality = remesa_registro.custom_total == common_filters.amount
	amount_rank = frappe.qb.terms.Case().when(amount_equality, 1).else_(0)
	amount_condition = amount_equality if exact_match else remesa_registro.custom_total > 0.0

	# party_condition = purchase_invoice.supplier == common_filters.party
	# party_rank = frappe.qb.terms.Case().when(party_condition, 1).else_(0)

	query = (
		frappe.qb.from_(remesa_registro)
		.select(
			(amount_rank).as_("rank"),
			ConstantColumn("Remesa Registro").as_("doctype"),
			remesa_registro.name,
			(remesa_registro.custom_total).as_("paid_amount"),
			ConstantColumn("").as_("reference_no"),
			ConstantColumn("").as_("reference_date"),
			ConstantColumn("").as_("party"),
			ConstantColumn("").as_("party_type"),
			(remesa_registro.fecha).as_("posting_date"),
			ConstantColumn("EUR").as_("currency"),
		)
		.where(amount_condition)
		.where(remesa_registro.custom_total_localizado != remesa_registro.custom_total)
		# .where(purchase_invoice.is_paid == 1)
	)

	return query

@frappe.whitelist()
def reconcile_vouchers_override(bank_transaction_name, vouchers, es_mismo_banco=False):
	vouchers = json.loads(vouchers)

	es_mismo_banco = json.loads(es_mismo_banco)

	# Conseguir cuenta bancaria actual de la transacción
	bank_transaction_doc = frappe.get_doc("Bank Transaction", bank_transaction_name)
	transaction_bank = frappe.db.get_value("Bank Account", bank_transaction_doc.bank_account, "bank")

	# Dividir y eliminar de los vouchers los que son Remesa Registro
	remesas = list(filter(lambda v: v.get("payment_doctype") == "Remesa Registro", vouchers))
	vouchers = list(filter(lambda v: v not in remesas, vouchers))

	for remesa in remesas:
		remesa_doc = frappe.get_doc("Remesa Registro", remesa.get("payment_name"))
		remesa_doc.cargar_campos_factura_pago(bank_transaction_doc.date, bank_transaction_doc.bank_account)
		frappe.db.commit()

		# Campo total localizado
		total_localizado = remesa_doc.custom_total_localizado

		for factura in remesa_doc.facturas:
			factura_doc = frappe.get_doc("Purchase Invoice", factura.factura)

			# Cerciorar de que los Payment Entry sean válidos para restar del total localizado, esto para evitar que
			# aparezca la remesa una vez conciliada.
			# payment_entries = frappe.db.get_all(
			# 	"Payment Entry Reference",
			# 	filters={"reference_doctype": "Purchase Invoice", "reference_name": factura.factura, "docstatus": 1},
			# 	fields=["parent", "total_amount"]
			# )

			pago_doc = frappe.get_doc("Payment Entry", factura.pago)

			if pago_doc:
				# if len(payment_entries) > 2:
				# 	payment_entries = list(filter(lambda p: p.posting_date == remesa_doc.fecha, payment_entries))
	
				payment_bank = frappe.get_value(
					"Bank Account", pago_doc.bank_account, "bank"
				)

				mew_pe_voucher = {
					"payment_doctype": "Payment Entry",
					"payment_name": pago_doc.name,
					"amount": pago_doc.paid_amount
				}

				# Verificar que el mismo banco del filtro sea el del pago
				if es_mismo_banco and transaction_bank == payment_bank:
					# Agregar el pago como voucher y sumar el monto del Payment Entry al total localizado
					vouchers.append(mew_pe_voucher)
					total_localizado += pago_doc.paid_amount

				if not es_mismo_banco:
					# Agregar el pago como voucher y sumar el monto del Payment Entry al total localizado
					vouchers.append(mew_pe_voucher)
					total_localizado += pago_doc.paid_amount
			else:
				# Si no se encuentran Payment Entry, agregar Purchase Invoice relacionada a la remesa como voucher
				## Buscar banco desde factura de compra
				purchase_bank = frappe.db.get_value(
					"Bank Account",
					{"party": factura_doc.supplier, "party_type": "Supplier"},
					"bank"
				)

				if es_mismo_banco and transaction_bank == purchase_bank:
					vouchers.append({
						"payment_doctype": "Purchase Invoice",
						"payment_name": factura_doc.name,
						"amount": factura_doc.grand_total
					})
					# Sumar el grand_total al total localizado
					total_localizado += factura_doc.grand_total

				if not es_mismo_banco and transaction_bank != purchase_bank:
					vouchers.append({
						"payment_doctype": "Purchase Invoice",
						"payment_name": factura_doc.name,
						"amount": factura_doc.grand_total
					})
					# Sumar el grand_total al total localizado
					total_localizado += factura_doc.grand_total

		remesa_doc.db_set("custom_total_localizado", total_localizado)

	return reconcile_vouchers(bank_transaction_name, json.dumps(vouchers))
