// Copyright (c) 2024, Xappiens and contributors
// For license information, please see license.txt

frappe.ui.form.on("Remesa Registro", {
    update_totals: function(frm) {
        console.log("Actualizando total");
        frm.call({
			doc: frm.doc,
            method: "set_total_importe",
        });
    }
});

frappe.ui.form.on("Remesa Factura", "importe", function(frm, cdt, cdn){
    console.log("cambiado importe");

    frm.trigger("update_totals");
});