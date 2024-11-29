
import json

import frappe
from frappe import _, throw
from frappe.model import child_table_fields, default_fields
from frappe.model.meta import get_field_precision
from frappe.model.utils import get_fetch_values
from frappe.query_builder.functions import IfNull, Sum
from frappe.utils import add_days, add_months, cint, cstr, flt, getdate

from erpnext import get_company_currency
from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
	get_pricing_rule_for_item,
	set_transaction_type,
)
from erpnext.setup.doctype.brand.brand import get_brand_defaults
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults
from erpnext.setup.utils import get_exchange_rate
from erpnext.stock.doctype.item.item import get_item_defaults, get_uom_conv_factor
from erpnext.stock.doctype.item_manufacturer.item_manufacturer import get_item_manufacturer_part_no
from erpnext.stock.doctype.price_list.price_list import get_price_list_details

from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice

import math



from collections import OrderedDict, defaultdict
from frappe import qb, scrub
from frappe.desk.reportview import get_filters_cond, get_match_cond
from frappe.query_builder import Criterion, CustomFunction
from frappe.query_builder.functions import Concat, Locate, Sum
from frappe.utils import nowdate, today, unique
from pypika import Order

import erpnext
from erpnext.stock.get_item_details import _get_item_tax_template

class CustomPurchaseInvoice(PurchaseInvoice):

    def calculate_taxes_and_totals(self):
        # Llamar a la lógica original de la clase base
        super().calculate_taxes_and_totals()
        if not self.inter_company_invoice_reference:
            # Calcular el total redondeado basado en el nuevo valor del total
            self.rounded_total = self.custom_round(self.grand_total)
            self.base_rounded_total = self.custom_round(self.base_grand_total)

            # Ajuste de redondeo calculado como la diferencia entre el total y el total redondeado
            self.rounding_adjustment = self.rounded_total - self.grand_total
            self.base_rounding_adjustment = self.base_rounded_total - self.base_grand_total

            # Calcular el monto pendiente basado en el total redondeado menos los pagos anticipados
            self.outstanding_amount = self.rounded_total - self.total_advance

            # Guardar los valores redondeados y ajustes en la base de datos
            self.db_set('rounded_total', self.rounded_total)
            self.db_set('base_rounded_total', self.base_rounded_total)
            self.db_set('rounding_adjustment', self.rounding_adjustment)
            self.db_set('base_rounding_adjustment', self.base_rounding_adjustment)
            self.db_set('outstanding_amount', self.outstanding_amount)

    def custom_round(self, value, decimals=2):
        """
        Redondea el segundo decimal hacia arriba basado en el tercer decimal.
        """
        shift = 10 ** decimals  # Queremos redondear al segundo decimal

        # Multiplicar para mover el punto decimal dos lugares a la derecha
        value_shifted = value * shift

        # Obtener el tercer decimal
        third_decimal = int((value_shifted * 10) % 10)

        # Si el tercer decimal es 5 o más, redondear hacia arriba el segundo decimal
        if third_decimal >= 5:
            value_shifted = math.ceil(value_shifted)
        else:
            value_shifted = math.floor(value_shifted)

        # Volver a mover el punto decimal a su lugar original
        return value_shifted / shift

    def set_status(self, update=False, status=None, update_modified=True):
        # Llamar a la lógica original de la clase base
        super().set_status(update=update, status=status, update_modified=update_modified)

        # Lógica adicional para el estado personalizado
        if self.docstatus == 0:  # Estado Borrador
            if self.custom_aprobado_para_pago and self.status != "Remesa Emitida":
                if self.status != "Aprobada para pago":
                    self.status = "Aprobada para pago"
                    self.db_set('status', self.status, update_modified=update_modified)
            
            if self.custom_remesa_emitida and self.status == "Aprobada para pago":
                self.status = "Remesa Emitida"
                self.db_set('status', self.status, update_modified=update_modified)

    def set_tax_withholding(self):
        # Llamar a la lógica original del método set_tax_withholding
        super().set_tax_withholding()

        # Obtener todas las cuentas de Tax Withholding Account para la compañía
        withholding_accounts = frappe.get_all("Tax Withholding Account", filters={"company": self.company}, fields=["account"])

        # Si `apply_tds` está desactivado o `tax_withholding_category` está vacío, eliminar la línea de IRPF
        if not self.tax_withholding_category or self.tax_withholding_net_total == 0:
            # Eliminar cualquier línea en taxes cuyo encabezado de cuenta esté en las cuentas de Tax Withholding Account
            self.taxes = [tax for tax in self.taxes if tax.account_head not in [acc['account'] for acc in withholding_accounts]]
            self.calculate_taxes_and_totals()
            return

        # Obtener los detalles de la categoría de retención de impuestos
        withholding_category = frappe.get_doc("Tax Withholding Category", self.tax_withholding_category)
        if not withholding_category or not withholding_category.rates:
            return

        # Obtener la primera tasa de retención
        withholding_rate = withholding_category.rates[0].tax_withholding_rate

        # Buscar la cuenta contable que coincida con la compañía de la factura
        account_head = None
        for account in withholding_category.accounts:
            if account.company == self.company:
                account_head = account.account
                break

        # Asegurarse de que se ha encontrado una cuenta contable
        if not account_head:
            frappe.throw(_("No se pudo encontrar una cuenta contable asociada a la retención de impuestos para la compañía {0}.").format(self.company))

        # Verificar si ya existe un impuesto con la misma cuenta o una cuenta en `Tax Withholding Account`
        tax_exists = False
        for tax in self.taxes:
            if tax.account_head == account_head or tax.account_head in [acc['account'] for acc in withholding_accounts]:
                # Si el impuesto existe o si una cuenta está en Tax Withholding Account, actualizar
                tax.charge_type = "Actual"
                tax.rate = withholding_rate
                tax.description = _("Retención IRPF ({0}%)").format(withholding_rate)
                tax.tax_amount = (self.tax_withholding_net_total * withholding_rate) / 100  # Calcular basado en tax_withholding_net_total
                tax_exists = True
                break

        # Si no existe, añadir una nueva fila a la tabla de impuestos
        if not tax_exists:
            self.append("taxes", {
                "charge_type": "Actual",
                "account_head": account_head,
                "description": _("Retención IRPF ({0}%)").format(withholding_rate),
                "rate": withholding_rate,
                "tax_amount": (self.tax_withholding_net_total * withholding_rate) / 100,  # Calcular basado en tax_withholding_net_total
                "category": "Total",
                "add_deduct_tax": "Deduct"
            })

        # Recalcular los totales después de agregar o eliminar el impuesto
        self.calculate_taxes_and_totals()

@frappe.whitelist()
def get_custom_item_tax_info(item_tax_template):
    tax_info = {}
    if item_tax_template:
        template = frappe.get_cached_doc("Item Tax Template", item_tax_template)
        for d in template.taxes:
            tax_info[d.tax_type] = {
                "tax_rate": d.tax_rate,
                "add_deduct_tax": d.add_deduct_tax
            }
    return tax_info

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_custom_expense_account(doctype, txt, searchfield, start, page_len, filters):
    from erpnext.controllers.queries import get_match_cond

    if not filters:
        filters = {}

    doctype = "Account"
    condition = ""
    if filters.get("company"):
        condition += "and tabAccount.company = %(company)s"

    # Condición para obtener las cuentas cuya cuenta root tiene el account number 2
    root_condition = ""
    if filters.get("company"):
        root_condition = "or (tabAccount.account_number LIKE '2%%' and tabAccount.company = %(company)s and tabAccount.is_group = 0)"

    return frappe.db.sql(
        f"""select tabAccount.name from `tabAccount`
        where (tabAccount.report_type = "Profit and Loss"
                or tabAccount.account_type in ("Expense Account", "Fixed Asset", "Temporary", "Asset Received But Not Billed", "Capital Work in Progress")
                {root_condition})
            and tabAccount.is_group=0
            and tabAccount.docstatus!=2
            and tabAccount.{searchfield} LIKE %(txt)s
            {condition} {get_match_cond(doctype)}""",
        {"company": filters.get("company", ""), "txt": "%" + txt + "%"},
    )
