$(document).ready(function() {
    $(document).on('page-change', function() {
        if (frappe.get_route()[0] === "print") {
            setTimeout(function() {
                if (frappe.ui.form.PrintView.prototype.printit) {
                    const originalPrintit = frappe.ui.form.PrintView.prototype.printit;

                    frappe.ui.form.PrintView.prototype.printit = function() {
                        let me = this;

                        frappe.call({
                            method: "integracion.integracion.custom_pdf_make.custom_download_and_attach_pdf",
                            args: {
                                doctype: me.frm.doc.doctype,
                                name: me.frm.doc.name,
                                format: me.selected_format(),
                                no_letterhead: !me.with_letterhead(),
                                letterhead: me.get_letterhead(),
                                settings: me.additional_settings,
                                _lang: me.lang_code,
                            },
                            callback: function(r) {
                                if (r && r.message) {
                                    frappe.msgprint(__('PDF adjunto correctamente'));
                                    originalPrintit.call(me);
                                } else {
                                    originalPrintit.call(me);
                                }
                            },
                            error: function(err) {
                                originalPrintit.call(me);
                            }
                        });
                    };
                }
            }, 1000);
        }
    });
});

