class CustomCommunicationComposer extends frappe.views.CommunicationComposer {
    
    get_fields() {
        let me = this;
        const fields = super.get_fields();
    
        fields.forEach(field => {
            if (field.fieldname === "select_print_format") {
                field.fieldtype = "Link";
                field.options = "Print Format";
                field.get_query = function() {
                    return {
                        filters: {
                            doc_type: me.frm.doctype
                        }
                    };
                };
    
                // Asignar el primer Print Format disponible como valor predeterminado
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Print Format",
                        filters: {
                            doc_type: me.frm.doctype
                        },
                        fields: ["name"],
                        limit: 1
                    },
                    callback: function(response) {
                        if (response.message && response.message.length > 0) {
                            me.dialog.set_value("select_print_format", response.message[0].name);
                        }
                    }
                });
            }
    
            if (field.fieldname === "print_language") {
                field.fieldtype = "Link";
                field.options = "Language";
            }
    
            if (field.fieldname === "print_language") {
                fields.push({
                    fieldtype: "Column Break"
                });
                fields.push({
                    label: __("Membrete"),
                    fieldtype: "Link",
                    fieldname: "letter_head",
                    options: "Letter Head",
                    depends_on: "attach_document_print",
                });
    
                // Asignar el primer Letter Head disponible como valor predeterminado
                frappe.call({
                    method: "frappe.client.get_list",
                    args: {
                        doctype: "Letter Head",
                        fields: ["name"],
                        limit: 1
                    },
                    callback: function(response) {
                        if (response.message && response.message.length > 0) {
                            me.dialog.set_value("letter_head", response.message[0].name);
                        }
                    }
                });
            }
        });
    
        return fields;
    }
    

    send_email(btn, form_values, selected_attachments, print_html, print_format) {
        const me = this;
        this.dialog.hide();

        if (!form_values.recipients) {
            frappe.msgprint(__("Enter Email Recipient(s)"));
            return;
        }

        if (!form_values.attach_document_print) {
            print_html = null;
            print_format = null;
        }

        return frappe.call({
            method: "frappe.core.doctype.communication.email.make",
            args: {
                recipients: form_values.recipients,
                cc: form_values.cc,
                bcc: form_values.bcc,
                subject: form_values.subject,
                content: form_values.content,
                doctype: me.doc.doctype,
                name: me.doc.name,
                send_email: 1,
                print_html: print_html,
                send_me_a_copy: form_values.send_me_a_copy,
                print_format: print_format,
                sender: form_values.sender,
                sender_full_name: form_values.sender ? frappe.user.full_name() : undefined,
                email_template: form_values.email_template,
                attachments: selected_attachments,
                read_receipt: form_values.send_read_receipt,
                print_letterhead: me.dialog.get_value("letter_head"),
                send_after: form_values.send_after ? form_values.send_after : null,
                print_language: form_values.print_language,
            },
            btn,
            callback(r) {
                if (!r.exc) {
                    frappe.utils.play_sound("email");

                    if (r.message["emails_not_sent_to"]) {
                        frappe.msgprint(
                            __("Email not sent to {0} (unsubscribed / disabled)", [
                                frappe.utils.escape_html(r.message["emails_not_sent_to"]),
                            ])
                        );
                    }

                    me.clear_cache();

                    if (me.frm) {
                        me.frm.reload_doc();
                    }

                    // try the success callback if it exists
                    if (me.success) {
                        try {
                            me.success(r);
                        } catch (e) {
                            console.log(e);
                        }
                    }
                } else {
                    frappe.msgprint(
                        __("There were errors while sending email. Please try again.")
                    );

                    // try the error callback if it exists
                    if (me.error) {
                        try {
                            me.error(r);
                        } catch (e) {
                            console.log(e);
                        }
                    }
                }
            },
        });
    }
}

// Luego, sobreescribe la clase original en tu aplicación:
frappe.views.CommunicationComposer = CustomCommunicationComposer;
