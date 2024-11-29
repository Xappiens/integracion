from erpnext.accounts.doctype.account import account
import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.pdf import get_pdf

import datetime
import json
import logging

from erpnext.accounts.report.financial_statements import get_data, get_period_list

from erpnext.accounts.utils import get_account_balances, get_balance_on
from integracion.utils.export_balance_sheet import account_div, set_accounts, calculate_totals, accounts_html, decimal, account_div

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler(
    '/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/export_profit_and_loss.log'
)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def get_net_profit_loss(income, expense, period_list, company, currency=None, consolidated=False):
	total = 0
	net_profit_loss = {
		"account_name": "'" + _("Profit for the year") + "'",
		"account": "'" + _("Profit for the year") + "'",
		"warn_if_negative": True,
		"currency": currency or frappe.get_cached_value("Company", company, "default_currency"),
	}

	has_value = False

	for period in period_list:
		key = period if consolidated else period.key
		total_income = flt(income[-2][key], 3) if income else 0
		total_expense = flt(expense[-2][key], 3) if expense else 0

		net_profit_loss[key] = total_income - total_expense

		if net_profit_loss[key]:
			has_value = True

		total += flt(net_profit_loss[key])
		net_profit_loss["total"] = total

	if has_value:
		return net_profit_loss

def get_profit_and_loss_data(filters):
    # Búsqueda de número de cuenta con query
    # account_query = f"""
    # SELECT account_number, name
    # FROM `tabAccount`
    # WHERE company = "{filters.company}" AND report_type = "Profit and Loss"
    # ORDER BY account_number
    # """

    # tabAccounts = frappe.db.sql(account_query, as_dict=True)

    # data = sorted(
    #     [{
    #         "balance": get_balance_on(
    #             start_date=filters.period_start_date,
    #             date=filters.period_end_date,
    #             account=e["name"],
    #             company=filters.company
    #         ) or 0,
    #         "account": e["name"],
    #         "account_number": int(e["account_number"] or 0),
    #     } for e in tabAccounts],
    #     key=lambda a: a["account"]
    # )

    # logger.info(data)
    acc_query = f"""
    SELECT
        account_number, name, lft, rgt
    FROM
        `tabAccount`
    WHERE
        company = "{filters.company}" AND report_type = "Profit and Loss"
    ORDER BY account_number
    """

    Accounts = frappe.db.sql(acc_query, as_dict=True)

    gl_query = f"""
    SELECT
        account.name, (SUM(gl_entry.debit) - SUM(gl_entry.credit)) AS balance, account.lft
    FROM
        `tabGL Entry` gl_entry
    LEFT JOIN
        `tabAccount` account ON account.name = gl_entry.account
    WHERE
        gl_entry.company = "{filters.company}"
        AND account.company = "{filters.company}"
        AND account.report_type = "Profit and Loss"
        AND gl_entry.posting_date >= "{filters.period_start_date}"
        AND gl_entry.posting_date <= "{filters.period_end_date}"
    GROUP BY account.name
    """

    GLEntries = frappe.db.sql(gl_query, as_dict=True)

    data = []

    for entry in Accounts:
        account_gl_entries = list(filter(lambda gl: gl["lft"] >= entry["lft"] and gl["lft"] <= entry["rgt"], GLEntries))
        if account_gl_entries:
            data.append({
                "balance": sum(a["balance"] for a in account_gl_entries),
                "account": entry["name"],
                "account_number": entry["account_number"]
            })

    return data

@frappe.whitelist()
def export_pdf(filters):
    filters = frappe._dict(json.loads(filters))

    company_name = filters.company
    today_date = datetime.date.today().strftime("%d/%m/%Y")
    from_date = datetime.datetime.strptime(filters.get("period_start_date"), "%Y-%m-%d").strftime("%d-%b")
    to_date = datetime.datetime.strptime(filters.get("period_end_date"), "%Y-%m-%d").strftime("%d-%b del %Y")
    formatted_today = datetime.datetime.strptime(today_date, "%d/%m/%Y").strftime("%d-%b del %Y")
    formatted_period = f"De {from_date} a {to_date}"

    data = get_profit_and_loss_data(filters)

    profit_and_loss_skeleton = [{
        "parent": "A.3) RESULTADO ANTES DE IMPUESTOS",
        "title_format": "h3",
        "children": [
            {
                "parent": "A.1) RESULTADO DE EXPLOTACIÓN",
                "title_format": "h3",
                "children": [
                    {
                        "parent": "I. Importe neto de la cifra de negocios.",
                        "children": [
                            {"parent": "a) Ventas.", "accounts": (700,701,702,703,704,"706","708","709")},
                            {"parent": "b) Prestaciones de servicios.", "accounts": (705, )},
                        ]
                    },
                    {
                        "parent": "2. Variación de existencias de productos terminados y en curso de fabricación.",
                        "accounts": ("6930", "71*", 7930)
                    },
                    {"parent": "3. Trabajos realizados por la empresa para su activo.", "accounts": (73, )},
                    {
                        "parent": "4. Aprovisionamientos.",
                        "children": [
                            {"parent": "a) Consumo de mercaderías.", "accounts": ("600", 6060, 6090, 6080, "610*")},
                            {
                                "parent": "b) Consumo de materias primas y otras materias consumibles.", "accounts": (
                                    "601", "602", 6061, 6062, 6081, 6082, 6091, 6092, "611*", "612*"
                                )
                            },
                            {"parent": "c) Trabajos realizados por otras empresas.", "accounts": ("607",)},
                            {
                                "parent": "d) Deterioro de mercaderías, materias primas y otros aprovisionamientos.",
                                "accounts": (
                                    "6931", "6932", "6933", 7931, 7932, 7933
                                )
                            }
                        ]
                    },
                    {
                        "parent": "5. Otros ingresos de explotación.",
                        "children": [
                            {"parent": "a) Ingresos accesorios y otros de gestión corriente.", "accounts": (75, )},
                            {
                                "parent": "b) Subvenciones de explotación incorporadas al resultado del ejercicio.",
                                "accounts": (740, 747)
                            }
                        ]
                    },
                    {
                        "parent": "6. Gastos de personal.",
                        "children": [
                            {"parent": "a) Sueldos, salarios y asimilados.", "accounts": ("640","641","6450")},
                            {"parent": "b) Cargas sociales.", "accounts": ("642","643","649")},
                            {"parent": "c) Provisiones.", "accounts": ("644", "6457", 7950, 7957)}
                        ]
                    },
                    {
                        "parent": "7. Otros gastos de explotación.",
                        "children": [
                            {"parent": "a) Servicios exteriores.", "accounts": ("62", )},
                            {"parent": "b) Tributos.", "accounts": ("631", "634", 636, 639)},
                            {
                                "parent": "c) Pérdidas, deterioro y variación de provisiones por operaciones comerciales.",
                                "accounts": ("650", "694", "695", 794, 7954)
                            },
                            {"parent": "d) Otros gastos de gestión corriente.", "accounts": ("651", "659")}
                        ]
                    },
                    {
                        "parent": "8. Amortización del inmovilizado.", "accounts": ("68", )
                    },
                    {
                        "parent": "9. Imputación de subvenciones de inmovilizado no financiero y otras.", "accounts": (746, )
                    },
                    {
                        "parent": "10. Excesos de provisiones.", "accounts": (7951, 7952, 7955, 7956)
                    },
                    {
                        "parent": "11. Deterioro y resultado por enajenaciones del inmovilizado.",
                        "children": [
                            {"parent": "a) Deterioros y pérdidas.", "accounts": ("690", "691", "692", 790, 791, 792)},
                            {
                                "parent": "b) Resultados por enajenaciones y otras.",
                                "accounts": ("670", "671", "672", 770, 771, 772)
                            }
                        ]
                    },
                    {
                        "parent": "13. Otros resultados",
                        "children": [
                            {"parent": "a) Ingresos excepcionales.", "accounts": ("678" ,778,)},
                        ]
                    },
                    {
                        "parent": "17. Impuestos sobre beneficios.",
                        "accounts": ("6300*", "6301*", "633", 638)
                    }
                ]
            },
            {
                "parent": "A.2) RESULTADO FINANCIERO",
                "title_format": "h3",
                "children": [
                    {
                        "parent": "12. Ingresos financieros.",
                        "children": [
                            {
                                "parent": "a) De participaciones en instrumentos de patrimonio.",
                                "children": [
                                    {"parent": "a₁) En empresas del grupo y asociadas.", "accounts": (7600, 7601)},
                                    {"parent": "a₂) En terceros", "accounts": (7602, 7603)}
                                ]
                            },
                            {
                                "parent": "b) De valores negociables y otros instrumentos financieros.",
                                "children": [
                                    {
                                        "parent": "b₁) De empresas del grupo y asociadas.",
                                        "accounts": (7610, 7611, 76200, 76201, 76210, 76211)
                                    },
                                    {
                                        "parent": "b₂) De terceros.",
                                        "accounts": (7612, 7613, 76202, 76203, 76212, 76213, 767, 769)
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "parent": "13. Gastos financieros.",
                        "children": [
                            {
                                "parent": "a) Por deudas con empresas del grupo y asociadas.",
                                "accounts": (
                                    "662","6610", "6611", "6615", "6616",
                                    "6640", "6641", "6650", "6651", "6654", "6655"
                                )
                            },
                            {
                                "parent": "b) Por deudas con terceros.",
                                "accounts": (
                                    "6612", "6613", "6617", "6618", "6642", "6643",
                                    "6652", "6653", "6656", "6657", "669",
                                )
                            },
                            {"parent": "c) Por actualización de provisiones.", "accounts": ("660", )},
                        ]
                    },
                    {
                        "parent": "14. Variación del valor razonable en instrumentos financieros.",
                        "children": [
                            {
                                "parent": "a) Valor razonable con cambios en pérdidas y ganancias.",
                                "accounts": ("6630", "6631", "6633", "6634", 7630, 7631, 7633, 7634)
                            },
                            {
                                "parent": "b) Transferencia de ajustes de valor razonable con cambios en el patrimonio neto.",
                                "accounts": ("6632",7632)
                            },
                        ]
                    },
                    {
                        "parent": "15. Diferencias de cambio.", "accounts": ("668", 768)
                    },
                    {
                        "parent": "16. Deterioro y resultado por enajenaciones de instrumentos financieros.",
                        "children": [
                            {
                                "parent": "a) Deterioros y pérdidas.", "accounts": (
                                    "696", "697", "698", "699", 796, 797, 798, 799
                                )
                            },
                            {
                                "parent": "b) Resultados por enajenaciones y otras.",
                                "accounts": ("666", "667", "673", "675", 766, 773, 775)
                            }
                        ]
                    }
                ]
            }
        ]
    },{
        "parent": "17. Impuestos sobre beneficios.",
        "title_format": "h3",
        "accounts": ("6300*", "6301*", "633" ,638)
    }]

    set_accounts(profit_and_loss_skeleton, data)
    calculate_totals(profit_and_loss_skeleton)

    header_html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                font-size: 12px;
                word-break: break-all;
                white-space: normal;
            }}
            .header {{
                margin-bottom: 15px;
            }}
            .header h1 {{
                font-size: 20px;
                text-align: left;
            }}
            .divider {{
                border-top: 2px solid black;
                margin: 10px 0;
            }}
            .full-widh {{
                style="width: 100%;
            }}
            .right {{
                float: right;
            }}
            .observations {{
                font-size: 12px;
                text-align: center;
                margin-bottom: 10px;
                padding: 5px;
                background-color: #f2f2f2;
                border: 1px solid black;
            }}
            .total {{
                font-size: 14px;
                margin-top: 10px;
                margin-bottom: 10px;
                padding: 5px;
                background-color: #808080;
                border: 1px solid black;
            }}
            .account {{
                width: 98%;
                margin-left: auto;
                font-size: 10px;
                text-transform: uppercase;
            }}
            .container {{
                width: 98%;
                margin-left: auto;
                margin-right: 0;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Cuenta de pérdidas y ganancias</h1>
            <div class="divider"></div>
            <table style="width: 100%;">
                <tr>
                    <td><b>Empresa:</b> {company_name}</td>
                    <td style="text-align: right;"><b>Fecha listado:</b> {formatted_today}</td>
                </tr>
                <tr>
                    <td><b>Observaciones</b></td>
                    <td style="text-align: right;"><b>Periodo:</b> {formatted_period}</td>
                </tr>
            </table>
            <div class="divider"></div>
        </div>
    </body>
    </html>
    """

    # Contenido del cuerpo directamente en el .py
    body_html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>

        <div class="observations"><b>A) OPERACIONES CONTINUADAS</b></div>
    """

    main_title = profit_and_loss_skeleton[0]

    for title in main_title["children"]:
        body_html += f"""
        <div class="container">
        """
        body_html = accounts_html(title["children"], title["title_format"], body_html)
        body_html += "</div>"

        body_html += f"""
        <div class="observations">
            <table style="width: 100%;">
                <tr>
                    <th style="text-align: left;">{title["parent"]}</th>
                    <th style="text-align: right;">{decimal(title.get("total"))}</th>
                </tr>
            </table>
        </div>
        """

    body_html += f"""
    <div class="observations">
        <table style="width: 100%;">
            <tr>
                <th style="text-align: left;">{main_title["parent"]}</th>
                <th style="text-align: right;">{decimal(main_title.get("total"))}</th>
            </tr>
        </table>
    </div>
    """

    a3_taxes = [profit_and_loss_skeleton[1]]
    body_html = accounts_html(a3_taxes, "h3", body_html)

    body_html += f"""
    <div class="observations">
        <table style="width: 100%;">
            <tr>
                <th style="text-align: left;">A.4) RESULTADO DEL EJERCICIO PROCEDENTE DE OPERACIONES CONTINUADAS</th>
                <th style="text-align: right;">{decimal(a3_taxes[0].get("total") + main_title.get("total"))}</th>
            </tr>
        </table>
    </div>
    <div class="observations">
        <table style="width: 100%;">
            <tr>
                <th style="text-align: left;">B) OPERACIONES INTERRUMPIDAS</th>
                <th style="text-align: right;">{decimal(0)}</th>
            </tr>
        </table>
    </div>
    <div class="width: 98%; margin: auto;">
        <div class="container">
            <table style="width: 100%;">
                <td><b>18. Resultado del ejercicio procedente de operaciones interrumpidas neto de impuestos.</b></td>
                <td style="text-align: right; padding-left: 20px;"><b>{decimal(0)}</b></td>
            </table>
        </div>
    </div>
    <div class="observations">
        <table style="width: 100%;">
            <tr>
                <th style="text-align: left;">A.5) RESULTADO DEL EJERCICIO</th>
                <th style="text-align: right;">{decimal(a3_taxes[0].get("total") + main_title.get("total"))}</th>
            </tr>
        </table>
    </div>
    """

    # Combinar el contenido del encabezado y el cuerpo
    html_content = header_html + body_html

    # Generar el archivo PDF
    pdf_content = get_pdf(html_content, {
        "header-spacing": 5,
        "footer-right": "Página: [page] de [toPage]"
    })

    # Generar nombre del archivo PDF
    file_name = "Perdida_Ganancia.pdf"

    # Guardar el archivo PDF
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "is_private": 1,
        "content": pdf_content
    })

    file_doc.save(ignore_permissions=True)

    return file_doc.file_url
