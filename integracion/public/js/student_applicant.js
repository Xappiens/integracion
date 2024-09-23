// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Student Applicant", {

	enroll: function(frm) {
		frappe.model.open_mapped_doc({
			method: "integracion.integracion.program_override.custom_enroll_student",
			frm: frm
		})
	}
});
