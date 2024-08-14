import frappe

@frappe.whitelist()
def filter_employees(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT name, employee_name
        FROM `tabEmployee`
        WHERE name LIKE %s OR employee_name LIKE %s
        LIMIT %s, %s
    """, ("%{}%".format(txt), "%{}%".format(txt), start, page_len))
