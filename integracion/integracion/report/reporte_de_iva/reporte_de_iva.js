// Copyright (c) 2024, Xappiens and contributors
// For license information, please see license.txt

frappe.query_reports["Reporte de IVA"] = {
    "filters": [
        {
            fieldname: "from_date",
            label: "Desde",
            fieldtype: "Date",
            mandatory: 0
        },
        {
            fieldname: "to_date",
            label: "Hasta",
            fieldtype: "Date",
            mandatory: 0
        },
        {
            fieldname: "type",
            label: "Tipo de Factura",
            fieldtype: "Select",
            options: "\nFactura de Compra\nFactura de Venta",
            mandatory: 0,
            default: "Factura de Compra"
        },
		{
            fieldname: "iva_type",
            label: "Tipo de IVA",
            fieldtype: "Select",
            options: "\n21\n10\n4",
            mandatory: 0,
            default: "21"
        },
		{
            fieldname: "valor",
            label: "Tipo de Valor",
            fieldtype: "Select",
            options: "\nPositiva\nNegativa",
            mandatory: 0,
            default: "Positiva"
        },
        {
            fieldname: "company",
            label: "Empresa",
            fieldtype: "Link",
            options: "Company",
            mandatory: 0,
            default: frappe.defaults.get_user_default("Company")
        }
    ],
    "onload": function (report) {
        report.page.add_inner_button(__("Exportar a Excel"), function () {
            let filters = report.get_values();
            frappe.call({
                method: "integracion.integracion.report.reporte_de_iva.reporte_de_iva.export_to_excel",
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
