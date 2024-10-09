// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Profit and Loss Statement"] = $.extend({}, erpnext.financial_statements);

erpnext.utils.add_dimensions("Profit and Loss Statement", 10);

frappe.query_reports["Profit and Loss Statement"]["filters"].push({
	fieldname: "selected_view",
	label: __("Select View"),
	fieldtype: "Select",
	options: [
		{ value: "Report", label: __("Report View") },
		{ value: "Growth", label: __("Growth View") },
		{ value: "Margin", label: __("Margin View") },
	],
	default: "Report",
	reqd: 1,
});

frappe.query_reports["Profit and Loss Statement"]["filters"].push({
	fieldname: "accumulated_values",
	label: __("Accumulated Values"),
	fieldtype: "Check",
	default: 1,
});

frappe.query_reports["Profit and Loss Statement"]["filters"].push({
	fieldname: "include_default_book_entries",
	label: __("Include Default FB Entries"),
	fieldtype: "Check",
	default: 1,
});

// Guarda la referencia del onload original
var original_onload = frappe.query_reports["Profit and Loss Statement"].onload;

// Extiende el onload del reporte "Profit and Loss Statement"
frappe.query_reports["Profit and Loss Statement"].onload = function(report) {
    // Ejecuta el onload original
    if (original_onload) {
        original_onload(report);
    }

    // Ahora, agrega tu lógica personalizada
    console.log("Custom Profit and Loss Statement JS loaded!", report.report_name);
	console.log(report.report_name);

    if (report.report_name === "Profit and Loss Statement") {
        // Agrega el botón solo para el reporte "Profit and Loss Statement"
        add_pals_export_but(report);
    }
	// Función que añade el botón "Exportar" con el menú desplegable

};

function add_pals_export_but(report) {
	// Crear un menú desplegable para la opción de exportación
	button = report.page.add_inner_button("Exportar PDF", () => export_profit_and_loss('PDF'));

	// Definir estilo del botón
	button[0].className = "btn btn-primary";
};

// Función para manejar la exportación
function export_profit_and_loss(format) {
	console.log(frappe.query_report.get_filter_values());
	frappe.call({
		method: "integracion.utils.export_profit_and_loss.export_pdf",
		args: {
			format: format,
			filters: frappe.query_report.get_filter_values()
		},
		callback: function (r) {
			if (r.message) {
				// Descargar el archivo generado
				window.open(r.message);
			}
		}
	});
};