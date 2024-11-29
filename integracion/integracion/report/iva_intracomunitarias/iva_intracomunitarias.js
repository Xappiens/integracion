// Copyright (c) 2024, Xappiens and contributors
// For license information, please see license.txt

frappe.query_reports["IVA Intracomunitarias"] = {
	"filters": [
		{
            fieldname: "company",
            label: "Empresa",
            fieldtype: "Link",
            options: "Company",
			mandatory: 1,
            default: frappe.defaults.get_user_default("Company"),
        },
		{
            fieldname: "from_date",
            label: "Desde",
            fieldtype: "Date",
            mandatory: 1
        },
        {
            fieldname: "to_date",
            label: "Hasta",
            fieldtype: "Date",
            mandatory: 1,
            default: frappe.datetime.get_today()
        },

	],
	"onload": function (report) {
        report.page.add_inner_button(__("Exportar a Excel"), function () {
            let filters = report.get_values();
            frappe.call({
                method: "integracion.integracion.report.trimestral_retenciones.trimestral_retenciones.export_to_excel",
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
