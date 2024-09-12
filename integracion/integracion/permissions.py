import frappe

def job_offer_query(user):
    if "Asesoría" in frappe.get_roles(user):
        return "`tabJob Offer`.docstatus = 1"
    return ""
