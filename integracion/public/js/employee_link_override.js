$(document).ready(function() {
    frappe.after_ajax(function() {
        $(document).on('form-load form-refresh', function(event, frm) {
            if (frm && frm.doc) {
                console.log("Form event triggered for: ", frm.doc);
                $.each(frm.fields_dict, function(fieldname, field) {
                    if (field.df.fieldtype === 'Link' && field.df.options === 'Employee') {
                        console.log("Found Link field to Employee: ", fieldname);
                        console.log("Value of the field: ", frm.doc[fieldname]); // Agregamos un log para ver el valor del campo
                        if (frm.doc[fieldname]) {
                            console.log("Value exists for field: ", fieldname); // Confirmar que entramos al if
                            frappe.call({
                                method: 'frappe.client.get_value',
                                args: {
                                    doctype: 'Employee',
                                    fieldname: 'employee_name',
                                    filters: { name: frm.doc[fieldname] }
                                },
                                callback: function(r) {
                                    if (r.message) {
                                        console.log("Employee name found: ", r.message.employee_name); // Confirmar que tenemos respuesta del servidor
                                        // Store the original ID
                                        var original_id = frm.doc[fieldname];
                                        
                                        // Set the display of the Link field to the employee name
                                        frm.fields_dict[fieldname].$input.val(r.message.employee_name);
                                        
                                        // Store the name in a custom attribute to retrieve later if needed
                                        frm.fields_dict[fieldname].$input.attr('data-original-id', original_id);

                                        // Update the label shown in the link field's displayed value
                                        frm.fields_dict[fieldname].$input.trigger('change');
                                        frm.fields_dict[fieldname].$input.trigger('input');
                                    }
                                }
                            });
                        }
                    }
                });
            }
        });
    });
});
