# account_override.py

import frappe
from erpnext.accounts.doctype.account.account import Account

class CustomAccount(Account):
    def set_root_and_report_type(self):
        # Bandera para detectar si los valores se han cambiado manualmente
        inherited_report_type = None
        inherited_root_type = None

        if self.parent_account:
            par = frappe.get_cached_value(
                "Account", self.parent_account, ["report_type", "root_type"], as_dict=1
            )

            # Hereda los valores de la cuenta padre si están disponibles
            if par.report_type:
                inherited_report_type = par.report_type
                if not self.is_group or self.report_type == inherited_report_type:
                    self.report_type = par.report_type  # Herencia predeterminada

            if par.root_type:
                inherited_root_type = par.root_type
                if not self.is_group or self.root_type == inherited_root_type:
                    self.root_type = par.root_type  # Herencia predeterminada

        # Si es un grupo y los valores han cambiado, actualiza las cuentas hijas
        if self.is_group:
            if self.report_type != inherited_report_type:
                frappe.db.sql(
                    "UPDATE `tabAccount` SET report_type=%s WHERE lft > %s AND rgt < %s",
                    (self.report_type, self.lft, self.rgt),
                )

            if self.root_type != inherited_root_type:
                frappe.db.sql(
                    "UPDATE `tabAccount` SET root_type=%s WHERE lft > %s AND rgt < %s",
                    (self.root_type, self.lft, self.rgt),
                )

        # Asigna un valor por defecto si solo se define el root_type y no el report_type
        if self.root_type and not self.report_type:
            self.report_type = (
                "Balance Sheet" if self.root_type in ("Asset", "Liability", "Equity") else "Profit and Loss"
            )
