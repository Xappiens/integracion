frappe.query_reports["Movimiento de Cuenta"] = {
    "filters": [
        {
            "fieldname": "from_date",
            "label": "Desde",
            "fieldtype": "Date",
            "mandatory": 1
        },
        {
            "fieldname": "to_date",
            "label": "Hasta",
            "fieldtype": "Date",
            "mandatory": 1
        },
        {
            "fieldname": "account",
            "label": "Cuenta",
            "fieldtype": "MultiSelectList",
            "mandatory": 1,
            "get_data": function(txt) {
                return frappe.db.get_link_options('Account', txt, {
                    company: frappe.query_report.get_filter_value('company'),
                    is_group: frappe.query_report.get_filter_value('is_group')
                });
            },
            "on_change": function() {
                let accounts = frappe.query_report.get_filter_value("account");
                if (accounts && accounts.length > 0) {
                    // Obtenemos la primera cuenta seleccionada para establecer los valores de company e is_group
                    let first_account = accounts[0].value;
                    frappe.db.get_value("Account", first_account, ["company", "is_group"], (value) => {
                        if (!frappe.query_report.get_filter_value("company")) {
                            frappe.query_report.set_filter_value("company", value.company);
                        }
                        if (frappe.query_report.get_filter_value("is_group") === undefined || frappe.query_report.get_filter_value("is_group") === null) {
                            frappe.query_report.set_filter_value("is_group", value.is_group);
                        }
                    });
                }
            }
        },
        {
            "fieldname": "company",
            "label": "Empresa",
            "fieldtype": "Link",
            "options": "Company"
        },
        {
            "fieldname": "is_group",
            "label": "Es Grupo",
            "fieldtype": "Check",
            "default": 0
        },
        {
            "fieldname": "account_type",
            "label": "Tipo de Cuenta",
            "fieldtype": "Select",
            "options": "\nEmpleado\nProfesional\nAlquiler",
            "default": "",
            "depends_on": "eval:true"
        },
        {
            "fieldname": "totals",
            "label": "Obtener Totales",
            "fieldtype": "Check",
            "default": 0
        }
    ],
    "onload": function (report) {
        report.page.add_inner_button(__("Exportar a Excel"), function () {
            let filters = report.get_values();
            frappe.call({
                method: "integracion.integracion.report.movimiento_de_cuenta.movimiento_de_cuenta.export_to_excel",
                args: { filters },
                callback: function (r) {
                    if (r.message) {
                        window.open(r.message);
                    }
                }
            });
        });
    }
};
