// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Balance Sheet"] = $.extend({}, erpnext.financial_statements);

frappe.query_reports["Balance Sheet"]["filters"].push({
	fieldname: "selected_view",
	label: __("Select View"),
	fieldtype: "Select",
	options: [
		{ value: "Report", label: __("Report View") },
		{ value: "Growth", label: __("Growth View") },
	],
	default: "Report",
	reqd: 1,
});

frappe.query_reports["Balance Sheet"]["filters"].push({
	fieldname: "accumulated_values",
	label: __("Accumulated Values"),
	fieldtype: "Check",
	default: 1,
});

frappe.query_reports["Balance Sheet"]["filters"].push({
	fieldname: "include_default_book_entries",
	label: __("Include Default FB Entries"),
	fieldtype: "Check",
	default: 1,
});

// // Evento onload para agregar el botón de exportación
// frappe.query_reports["Balance Sheet"]["onload"] = function (report) {
//     console.log("Custom Balance Sheet JS loaded!",report.report_name);

//     // Verifica si es el reporte "Balance Sheet"
//     if (report.report_name === "Balance Sheet") {
//         // Agrega el botón solo para el reporte "Balance Sheet"
//         add_bs_export_but(report);
//     }

//     console.log(report);
// };

// Guarda la referencia del onload original
var original_onload = frappe.query_reports["Balance Sheet"].onload;

// Extiende el onload del reporte "Balance Sheet"
frappe.query_reports["Balance Sheet"].onload = function(report) {
    // Ejecuta el onload original
    if (original_onload) {
        original_onload(report);
    }

    // Ahora, agrega tu lógica personalizada
    console.log("Custom Balance Sheet JS loaded!", report.report_name);

    if (report.report_name === "Balance Sheet") {
        // Agrega el botón solo para el reporte "Balance Sheet"
        add_bs_export_but(report);
    }

    console.log(report);
};


// Evento refresh para asegurar que el botón esté presente tras refrescar el informe
frappe.query_reports["Balance Sheet"]["refresh"] = function (report) {
    // Verifica si es el reporte "Balance Sheet"
    if (report.report_name === "Balance Sheet") {
        // Agrega el botón solo para el reporte "Balance Sheet"
        add_bs_export_but(report);
    }
};

// Función que añade el botón "Exportar" con el menú desplegable
function add_bs_export_but(report) {
    // Crear un menú desplegable para las opciones de exportación
    button = report.page.add_inner_button("Exportar PDF", () => export_balance_sheet('PDF'));

    // Definir estilo del botón
    button[0].className = "btn btn-primary";
}

// Función para manejar la exportación
function export_balance_sheet(format) {
    frappe.call({
        method: "integracion.utils.export_balance_sheet.export_balance_sheet",
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
}

erpnext.utils.add_dimensions("Balance Sheet", 10);