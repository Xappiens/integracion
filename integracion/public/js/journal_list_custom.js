frappe.listview_settings['Journal Entry'] = {
    onload: function(listview) {
        logger.info("TEST")
        // Añadir un botón personalizado a la vista de lista de Journal Entry
        listview.page.add_menu_item(__('Importar Asientos Nóminas'), function() {
            frappe.prompt([
                {
                    fieldname: 'company',
                    label: __('Company'),
                    fieldtype: 'Link',
                    options: 'Company',
                    reqd: 1
                },
                {
                    fieldname: 'xml_file',
                    label: __('Archivo XML'),
                    fieldtype: 'Attach',
                    reqd: 1
                }
            ], function(values) {
                if (!values.company) {
                    frappe.msgprint(__('Por favor, selecciona una empresa.'));
                    return;
                }

                // Bloquear la página mientras se ejecuta el proceso
                frappe.show_alert({message: __('Procesando... Por favor espera.'), indicator: 'blue'});
                frappe.dom.freeze(__('Procesando...'));

                frappe.call({
                    method: 'integracion.subir_nominas',
                    args: {
                        company: values.company,
                        xml_file: values.xml_file
                    },
                    callback: function(response) {
                        frappe.dom.unfreeze();  // Desbloquear la página
                        if (response.message) {
                            let files = response.message;

                            // Mostrar un popup con los botones de descarga de los archivos generados
                            frappe.msgprint(`
                                <p>Proceso completado. Descarga los archivos generados:</p>
                                <a href="${files.error_log}" download>Descargar log de errores</a><br>
                                <a href="${files.excel_no_cuenta_o_empleado}" download>Descargar Excel (Usuarios sin cuenta o empleado)</a><br>
                                <a href="${files.fallo_xml}" download>Descargar XML de fallos</a>
                            `);
                        } else {
                            frappe.msgprint(__('Error durante el proceso. Por favor, revisa el archivo XML.'));
                        }
                    },
                    error: function() {
                        frappe.dom.unfreeze();
                        frappe.msgprint(__('Ocurrió un error al procesar el archivo.'));
                    }
                });
            }, __('Importar Asientos Nóminas'), __('Crear'));
        });
    }
};
