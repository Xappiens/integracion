frappe.provide("erpnext.accounts.bank_reconciliation");

frappe.ui.form.on("Bank Reconciliation Tool", {
    render(frm) {


        class CustomDialogManager extends erpnext.accounts.bank_reconciliation.DialogManager {
            constructor(
                company,
                bank_account,
                bank_statement_from_date,
                bank_statement_to_date,
                filter_by_reference_date,
                from_reference_date,
                to_reference_date
            ) {
                super(
                    company,
                    bank_account,
                    bank_statement_from_date,
                    bank_statement_to_date,
                    filter_by_reference_date,
                    from_reference_date,
                    to_reference_date
                )
                $.extend(
                    company,
                    bank_account,
                    bank_statement_from_date,
                    bank_statement_to_date,
                    filter_by_reference_date,
                    from_reference_date,
                    to_reference_date
                )
            }
            match() {
                var selected_map = this.datatable.rowmanager.checkMap;
                let rows = [];
                selected_map.forEach((val, index) => {
                    if (val == 1) rows.push(this.datatable.datamanager.rows[index]);
                });
                let vouchers = [];
                rows.forEach((x) => {
                    vouchers.push({
                        payment_doctype: x[2].content,
                        payment_name: x[3].content,
                        amount: x[5].content,
                    });
                });
                frappe.call({
                    method: "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.reconcile_vouchers",
                    args: {
                        bank_transaction_name: this.bank_transaction.name,
                        vouchers: vouchers,
                        es_mismo_banco: this.get_selected_attributes().includes("es_mismo_banco")
                    },
                    callback: (response) => {
                        const alert_string = __("Bank Transaction {0} Matched", [this.bank_transaction.name]);
                        frappe.show_alert(alert_string);
                        this.update_dt_cards(response.message);
                        this.dialog.hide();
                    },
                });
            }
        }

        erpnext.accounts.bank_reconciliation.DialogManager = CustomDialogManager;

        class CustomDataTableManager extends erpnext.accounts.bank_reconciliation.DataTableManager {
            constructor(opts) {
                super(opts);
                $.extend(opts);

                this.dialog_manager = new erpnext.accounts.bank_reconciliation.DialogManager(
                    this.company,
                    this.bank_account,
                    this.bank_statement_from_date,
                    this.bank_statement_to_date,
                    this.filter_by_reference_date,
                    this.from_reference_date,
                    this.to_reference_date
                );
            }
        }

        erpnext.accounts.bank_reconciliation.DataTableManager = CustomDataTableManager;

		if (frm.doc.bank_account) {
            new erpnext.accounts.bank_reconciliation.DataTableManager({
                company: frm.doc.company,
                bank_account: frm.doc.bank_account,
                $reconciliation_tool_dt: frm.get_field("reconciliation_tool_dt").$wrapper,
                $no_bank_transactions: frm.get_field("no_bank_transactions").$wrapper,
                bank_statement_from_date: frm.doc.bank_statement_from_date,
                bank_statement_to_date: frm.doc.bank_statement_to_date,
                filter_by_reference_date: frm.doc.filter_by_reference_date,
                from_reference_date: frm.doc.from_reference_date,
                to_reference_date: frm.doc.to_reference_date,
                bank_statement_closing_balance: frm.doc.bank_statement_closing_balance,
                cards_manager: frm.cards_manager,
            });
        }
    },

	make_reconciliation_tool(frm) {
		frm.get_field("reconciliation_tool_cards").$wrapper.empty();
		if (frm.doc.bank_account && frm.doc.bank_statement_to_date) {
			frm.trigger("get_cleared_balance").then(() => {
				if (
					frm.doc.bank_account &&
					frm.doc.bank_statement_from_date &&
					frm.doc.bank_statement_to_date
				) {
					frm.trigger("render_chart");
					frm.trigger("render");
					frappe.utils.scroll_to(frm.get_field("reconciliation_tool_cards").$wrapper, true, 30);
				}
			});
		}
	},
});