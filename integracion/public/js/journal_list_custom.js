frappe.listview_settings['Journal Entry'] = {
    onload: function(listview) {
        console.log("Lista cargada");

        // Crear menú de herramientas
        listview.page.add_menu_item(__('Herramientas'), function() {}, true);

        // Recuperar el estado actual del progreso de nóminas
        frappe.call({
            method: 'integracion.integracion.subir_nominas.get_nominas_progreso',
            callback: function(response) {
                let progress = response.message;
                if (progress && progress.progreso < progress.total_asientos) {
                    frappe.show_progress(
                        __('Procesando Nóminas'),
                        progress.progreso,
                        progress.total_asientos,
                        __('Continuando proceso...')
                    );

                    frappe.realtime.on("subir_nominas_progress", function(data) {
                        if (data.progress) {
                            frappe.show_progress(__('Procesando Nóminas'), data.progress[0], data.progress[1], data.message);
                        }
                    });
                }
            }
        });

        // Suscribirse al canal de progreso para importación de diario
        frappe.realtime.on("import_journal_entries_progreso", function(data) {
            if (!data.success) {
                frappe.show_progress(__('Procesando diario de asientos'), data.progress[0], data.progress[1], data.message);
            } else {
                frappe.hide_progress(__('Procesando diario de asientos'));
                let msg = ``;
                msg += `<p>Proceso completado. Se han creado ${data.asientos} líneas de asiento</p><br>`;
                if (data.error_file) {
                    msg += `<p>Hay ${data.errores} ${(data.errores > 1) ? "asientos": "asiento"} con errores</p><br>`;
                    msg += `<a href="${data.error_file}" download>Descargar Excel de fallos</a><br>`;
                }
                frappe.msgprint(msg);
            }
        });

        // Añadir opción de Importar Nóminas al menú
        listview.page.add_menu_item(__('Importar Nóminas'), function() {
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

                frappe.show_alert({message: __('Procesando... Por favor espera.'), indicator: 'blue'});

                frappe.realtime.on("subir_nominas_progress", function(data) {
                    if (data.progress) {
                        frappe.hide_msgprint(true);
                        frappe.show_progress(__('Procesando Nóminas'), data.progress[0], data.progress[1], data.message);
                    }
                    if (data.progress[0] === data.progress[1]) {
                        frappe.hide_progress();
                        frappe.realtime.off("subir_nominas_progress");
                    }
                });

                frappe.call({
                    method: 'integracion.subir_nominas',
                    args: {
                        company: values.company,
                        xml_file: values.xml_file
                    },
                    callback: function(response) {
                        if (response.message) {
                            let files = response.message;
                            if (files.error_log || files.fallo_xml) {
                                let download_links = '';
                                if (files.error_log) {
                                    download_links += `<a href="${files.error_log}" download>Descargar log de errores</a><br>`;
                                }
                                if (files.fallo_xml) {
                                    download_links += `<a href="${files.fallo_xml}" download>Descargar XML de fallos</a><br>`;
                                }
                                frappe.msgprint(`
                                    <p>Proceso completado. Descarga los archivos generados:</p>
                                    ${download_links}
                                `);
                            } else {
                                frappe.msgprint(__('Proceso completado con éxito. No hubo errores.'));
                            }
                        } else {
                            frappe.msgprint(__('Error durante el proceso. Por favor, revisa el archivo XML.'));
                        }
                    },
                    error: function() {
                        frappe.realtime.off("subir_nominas_progress");
                        frappe.hide_progress();
                        frappe.msgprint(__('Ocurrió un error al procesar el archivo.'));
                    }
                });
            }, __('Importar Asientos Nóminas'), __('Crear'));
        }, true, 'Herramientas');

        // Añadir opción de Importar diario de asientos al menú
        listview.page.add_menu_item(__('Importar diario de asientos'), function() {
            frappe.prompt(
                [
                    {
                        fieldname: 'company',
                        label: __('Company'),
                        fieldtype: 'Link',
                        options: 'Company',
                        reqd: 1,
                        default: frappe.defaults.get_user_default("Company"),
                    },
                    {
                        fieldname: 'excel_file',
                        label: __('Archivo Excel'),
                        fieldtype: 'Attach',
                        reqd: 1
                    }
                ],
                (values) => {
                    frappe.call({
                        method: 'integracion.import_journal_entries',
                        args: {
                            excel_file: values.excel_file,
                            company: values.company
                        },
                        callback: function(r) {
                            if (r.message) {
                                window.open(r.message);
                            }
                        }
                    });
                },
                __('Importar diario de asientos'),
                __('Importar')
            );
        }, true, 'Herramientas');

        // Añadir separador en el menú
        listview.page.add_menu_item('', function(){}, true, 'Herramientas');

        // Añadir opción de Renumerar al menú (separada)
        listview.page.add_menu_item(__('Renumerar'), function() {
            frappe.confirm(
                __('¿Está seguro de que desea renumerar los Journal Entries? Esta acción no se puede deshacer.'),
                function() {
                    frappe.prompt([
                        {
                            fieldtype: 'Link',
                            options: 'Company',
                            label: __('Empresa'),
                            fieldname: 'company',
                            reqd: 1
                        },
                        {
                            fieldtype: 'Int',
                            label: __('Año'),
                            fieldname: 'year',
                            reqd: 1,
                            default: new Date().getFullYear(),
                            description: __('Año entre 1900 y 2100')
                        }
                    ],
                    function(values) {
                        if (values.year < 1900 || values.year > 2100) {
                            frappe.throw(__('El año debe estar entre 1900 y 2100'));
                            return;
                        }

                        // Suscribirse al canal de progreso
                        frappe.realtime.on("renumerar_journal_entries_progress", function(data) {
                            if (!data.success) {
                                if (data.progress) {
                                    frappe.show_progress(
                                        __('Renumerando asientos'),
                                        data.progress[0],
                                        data.progress[1],
                                        data.message
                                    );
                                }
                            } else {
                                frappe.hide_progress();
                                frappe.realtime.off("renumerar_journal_entries_progress");
                                frappe.show_alert({
                                    message: __(`Renumeración completada. Se han renumerado ${data.total_renumerados} asientos.`),
                                    indicator: 'green'
                                }, 5);
                                listview.refresh();
                            }
                        });

                        frappe.call({
                            method: "integracion.renumerar_asientos",
                            args: {
                                company: values.company,
                                year: values.year
                            },
                            callback: function(r) {
                                if (!r.message) {
                                    frappe.realtime.off("renumerar_journal_entries_progress");
                                    frappe.hide_progress();
                                    frappe.show_alert({
                                        message: __('Error al renumerar los asientos contables'),
                                        indicator: 'red'
                                    }, 5);
                                }
                            },
                            error: function(r) {
                                frappe.realtime.off("renumerar_journal_entries_progress");
                                frappe.hide_progress();
                                frappe.show_alert({
                                    message: __('Error al renumerar los asientos contables'),
                                    indicator: 'red'
                                }, 5);
                            }
                        });
                    },
                    __('Renumerar Journal Entries'),
                    __('Renumerar')
                    );
                }
            );
        }, true, 'Herramientas');
    }
};