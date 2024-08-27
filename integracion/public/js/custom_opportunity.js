// custom_opportunity.js

// Asegúrate de que el espacio de nombres de ERPNext está disponible
frappe.provide("erpnext.crm");

frappe.ui.form.on("Opportunity", {
    setup: function (frm) {
        // Llamar a la funcionalidad original si fuera necesario
        if (typeof frm.custom_make_buttons === "undefined") {
            frm.custom_make_buttons = {
                Quotation: "Quotation",
                "Supplier Quotation": "Supplier Quotation",
            };
        }

        // Modificar el filtro para incluir "Supplier" y "Sales Person"
        frm.set_query("opportunity_from", function () {
            return {
                filters: {
                    name: ["in", ["Customer", "Lead", "Prospect", "Supplier", "Sales Person"]],
                },
            };
        });

        frm.email_field = "contact_email";
    },

    // Aquí puedes extender otros métodos que necesites
    refresh: function (frm) {
        // Puedes llamar al método original o agregar tu lógica aquí
        // super.refresh(); // Esto se usaría si tuvieras una clase base que quieras llamar
    }
});
