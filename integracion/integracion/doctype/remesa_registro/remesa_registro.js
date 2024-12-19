frappe.ui.form.on("Remesa Registro", {
    update_totals: function (frm) {
        console.log("Actualizando total");
        frm.call({
            doc: frm.doc,
            method: "set_total_importe",
        });
    },

    refresh(frm) {
        if (!frm.is_dirty()) {
            frm.add_custom_button(
                __("Calcular totales"),
                () => {
                    frm.call("set_total_importe").then(() => frm.refresh());
                },
                __("Herramientas"),
            );
            frm.add_custom_button(
                __("Actualizar campos de factura y pago"),
                () => {
                    frappe.prompt(
                        [
                            {
                                fieldname: "date",
                                label: __("Date"),
                                fieldtype: "Date",
                                reqd: 1,
                            },
                            {
                                fieldname: "bank_account",
                                label: __("Bank Account"),
                                fieldtype: "Link",
                                options: "Bank Account",
                                reqd: 1,
                            }
                        ],
                        (values) => {
                            frm.call("cargar_campos_factura_pago", {
                                date: values.date,
                                bank_account: values.bank_account
                            }).then(() => frm.refresh());
                        },
                        __("Actualizar campos de factura y pago"),
                        __("Aceptar"),
                    );
                },
                __("Herramientas"),
            );
        }
        if (!frm.is_dirty() && frm.doc.custom_total_localizado > 0) {
            frm.add_custom_button(
                __("Quitar conciliación"),
                () => {
                    frm.call("eliminar_conciliacion").then(() => frm.refresh());
                },
                __("Herramientas"),
            );
        }
    },
});

frappe.ui.form.on("Remesa Factura", "importe", function (frm, cdt, cdn) {
    console.log("cambiado importe");
    frm.trigger("update_totals");
});