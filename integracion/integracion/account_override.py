# account_override.py

import frappe
from erpnext.accounts.doctype.account.account import Account

class CustomAccount(Account):
    def set_root_and_report_type(self):
        if self.parent_account:
            par = frappe.get_cached_value(
                "Account", self.parent_account, ["report_type", "root_type"], as_dict=1
            )

            # Modificación: Si el padre es raíz, permite editar y no forzar la herencia
            is_root_account = not frappe.db.get_value("Account", self.parent_account, "parent_account")

            if par.report_type and not is_root_account:
                self.report_type = par.report_type  # Solo hereda si no es una cuenta raíz

            if par.root_type and not is_root_account:
                self.root_type = par.root_type  # Solo hereda si no es una cuenta raíz

        # Mantener la lógica existente para ajustar el tipo de reporte si es necesario
        if self.is_group:
            db_value = self.get_doc_before_save()
            if db_value:
                if self.report_type != db_value.report_type:
                    frappe.db.sql(
                        "update `tabAccount` set report_type=%s where lft > %s and rgt < %s",
                        (self.report_type, self.lft, self.rgt),
                    )
                if self.root_type != db_value.root_type:
                    frappe.db.sql(
                        "update `tabAccount` set root_type=%s where lft > %s and rgt < %s",
                        (self.root_type, self.lft, self.rgt),
                    )

        # Si el root_type está presente pero el report_type no lo está, lo asignamos por defecto
        if self.root_type and not self.report_type:
            self.report_type = (
                "Balance Sheet" if self.root_type in ("Asset", "Liability", "Equity") else "Profit and Loss"
            )
