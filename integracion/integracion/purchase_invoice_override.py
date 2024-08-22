from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
import frappe
from frappe import _
import math

class CustomPurchaseInvoice(PurchaseInvoice):

    def calculate_taxes_and_totals(self):
        # Llamar a la lógica original de la clase base
        super().calculate_taxes_and_totals()

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
        if not self.apply_tds or not self.tax_withholding_category:
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
                tax.charge_type = "On Net Total"
                tax.rate = withholding_rate
                tax.description = _("Retención IRPF ({0}%)").format(withholding_rate)
                tax.tax_amount = None  # Dejar que se calcule automáticamente
                tax_exists = True
                break

        # Si no existe, añadir una nueva fila a la tabla de impuestos
        if not tax_exists:
            self.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": account_head,
                "description": _("Retención IRPF ({0}%)").format(withholding_rate),
                "rate": withholding_rate,
                "tax_amount": None,  # Dejar que se calcule automáticamente
                "category": "Total",
                "add_deduct_tax": "Deduct"
            })

        # Recalcular los totales después de agregar o eliminar el impuesto
        self.calculate_taxes_and_totals()
