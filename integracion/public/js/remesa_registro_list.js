frappe.listview_settings["Remesa Registro"] = {
    onload: function (listview) {
        listview.page.add_action_item(__("Calcular totales"), function () {
            listview.call_for_selected_items(
                "integracion.integracion.doctype.remesa_registro.remesa_registro.calcular_totales",
            );
        });
    },
};
