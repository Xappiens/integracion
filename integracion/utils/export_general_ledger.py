import os
import frappe
from frappe.utils.pdf import get_pdf
from frappe.utils.jinja import render_template
from frappe import _
import json
import datetime

@frappe.whitelist()
def export_general_ledger(format, filters):
    if isinstance(filters, str):
        filters = json.loads(filters)

    # Obtener los datos del General Ledger según los filtros
    general_ledger_data = get_general_ledger_data(filters)

    if format == "PDF":
        today_date = datetime.date.today().strftime("%d/%m/%Y")
        
        # Formatear periodo
        from_date = datetime.datetime.strptime(filters.get("from_date"), "%Y-%m-%d").strftime("%d-%b")
        to_date = datetime.datetime.strptime(filters.get("to_date"), "%Y-%m-%d").strftime("%d-%b del %Y")
        formatted_period = f"De {from_date} a {to_date}"

        # Totales
        total_debit = sum([entry.get('debit', 0) for entry in general_ledger_data])
        total_credit = sum([entry.get('credit', 0) for entry in general_ledger_data])

        # Generar contenido HTML del reporte
        html_content = render_template("integracion/templates/gl_template.html", {
            "data": general_ledger_data,
            "company": filters.get("company"),
            "today_date": today_date,
            "formatted_period": formatted_period,
            "account": filters.get("account")[0] if filters.get("account") else filters.get("party_name", ""),
            "total_debit": total_debit,
            "total_credit": total_credit,
            "page_number": 1  # Este campo no se usará directamente, wkhtmltopdf maneja la paginación
        })

        # Generar contenido HTML del encabezado
        header_html = render_template("integracion/templates/header_template.html", {
            "company": filters.get("company"),
            "today_date": today_date,
            "formatted_period": formatted_period,
            "account": filters.get("account")[0] if filters.get("account") else filters.get("party_name", ""),
        })

        # Guardar el archivo HTML del encabezado temporalmente
        header_file_path = os.path.join(frappe.utils.get_site_path(), 'public', 'files', 'header_template.html')
        with open(header_file_path, 'w') as f:
            f.write(header_html)

        # Generar PDF con encabezado en cada página
        pdf_content = get_pdf(html_content, {
            "orientation": "Landscape",
            "header-html": header_file_path,
            "header-spacing": -30,
            "margin-top": 30,
        })
        # Guardar el archivo PDF
        file_name = "General_Ledger_Report.pdf"
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "is_private": 1,
            "content": pdf_content
        })
        file_doc.save(ignore_permissions=True)

        return file_doc.file_url



def get_general_ledger_data(filters):
    query_conditions = []
    query_filters = {
        "company": filters.get("company"),
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }
    
    query_conditions.append("company = %(company)s")
    query_conditions.append("posting_date BETWEEN %(from_date)s AND %(to_date)s")
    
    # Aplicar filtro para "party" si no está vacío
    if filters.get("party"):
        # Usar el filtro directamente con parámetros en lugar de concatenar
        query_conditions.append("party IN %(party)s")
        query_filters["party"] = tuple(filters.get("party"))
    
    # Aplicar filtro para "account" si no está vacío
    if filters.get("account"):
        # Usar el filtro directamente con parámetros en lugar de concatenar
        query_conditions.append("account IN %(account)s")
        query_filters["account"] = tuple(filters.get("account"))
    
    # Construir la consulta final usando parámetros
    query = f"""
        SELECT posting_date, account, voucher_no, party_type, party, debit, credit,
               (debit - credit) AS balance
        FROM `tabGL Entry`
        WHERE {" AND ".join(query_conditions)}
        ORDER BY posting_date ASC
    """
    
    data = frappe.db.sql(query, query_filters, as_dict=True)
    
    # Obtener el concepto traducido (doctype)
    for entry in data:
        voucher_doctype = frappe.db.get_value("GL Entry", entry["voucher_no"], "voucher_type")
        if voucher_doctype:
            # Traducir el Doctype al idioma del usuario
            translated_doctype = _(frappe.get_meta(voucher_doctype).get_label())
            entry["concept"] = translated_doctype
        else:
            entry["concept"] = _("Unknown")

    return data
