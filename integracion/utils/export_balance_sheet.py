import os
import frappe
from frappe.utils.pdf import get_pdf

from frappe import _
import json
import datetime

import logging 

from erpnext.accounts.report.financial_statements import get_data, get_period_list
from babel.numbers import format_decimal

# Configurar el logger
logger = logging.getLogger(__name__)
handler = logging.FileHandler('/home/frappe/frappe-bench/apps/integracion/integracion/integracion/logs/export_balance_sheet.log')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Funciones auxiliares
def has_children(to_check):
    if "children" in to_check:
        return True

    return False

def has_accounts(to_check):
    if "accounts" in to_check:
        return True

    return False

def set_accounts(balance_structure, balance_sheet_data):
    for parent in balance_structure:
        if has_accounts(parent):
            parent_accounts = filter_accounts(parent["accounts"], balance_sheet_data)
            balance_total = sum(ia['balance'] for ia in parent_accounts)
            parent["accounts"] = parent_accounts
            parent["total"] = balance_total

        elif has_children(parent):
            set_accounts(parent["children"], balance_sheet_data)

def calculate_totals(balance_structure):
    for parent in balance_structure:
        if 'children' in parent:
            calculate_totals(parent['children'])

            total = sum(child.get('total', 0) for child in parent['children'] if 'total' in child)
            parent['total'] = total

# # Función auxiliar para obtener los datos del General Ledger
def get_balance_sheet_data(filters):
    period_list = get_period_list(
        filters.from_fiscal_year, filters.to_fiscal_year, filters.period_start_date, filters.period_end_date,
        filters.filter_based_on, filters.periodicity, company=filters.company,
	)

    filters.period_start_date = period_list[0]["year_start_date"]

    asset = get_data(
        filters.company, "Asset", "Debit", period_list, only_current_fiscal_year=False, filters=filters,
        accumulated_values=filters.accumulated_values,
	)

    liability = get_data(
		filters.company, "Liability", "Credit", period_list, only_current_fiscal_year=False, filters=filters,
		accumulated_values=filters.accumulated_values,
	)

    equity = get_data(
		filters.company, "Equity", "Credit", period_list, only_current_fiscal_year=False, filters=filters,
		accumulated_values=filters.accumulated_values,
	)

    data = []
    data.extend(asset or [])
    data.extend(liability or [])
    data.extend(equity or [])

    data = sorted(
        [{"balance": e["total"], "account": e["account"], "account_number": 0} for e in data if e],
        key=lambda a: a["account"]
    )

    # Búsqueda de número de cuenta con query
    account_query = f"""
    SELECT account_number, name
    FROM `tabAccount`
    WHERE company = "{filters.company}"
    ORDER BY account_number
    """

    tabAccounts = frappe.db.sql(account_query, as_dict=True)

    for entry in data:
        account_number = list(filter(lambda a: a["name"] == entry["account"], tabAccounts))

        if len(account_number):
            entry.update({"account_number": account_number[0]["account_number"]})

    return data

def filter_accounts(account_numbers, balance_data):
    negative_accounts = list(filter(lambda an: type(an) == str, account_numbers))
    account_numbers = list(map(int, account_numbers))

    res = tuple(filter(
        lambda bd: int(bd["account_number"]) in account_numbers,
        sorted(balance_data, key=lambda bd: int(bd["account_number"]))
    ))

    for entry in res:
        if str(entry["account_number"]) in negative_accounts:
            if entry["balance"] > 0:
                logger.info(entry)

                entry["balance"] = -entry["balance"]
        else:
            entry["balance"] = abs(entry["balance"])

    return res

def decimal(number):
    return format_decimal(round(number, 2), locale="es_ES")

@frappe.whitelist()
def export_balance_sheet(format, filters):
    # Guardar filtros originales
    org_filters = frappe._dict()

    if isinstance(filters, str):
        filters = json.loads(filters)
        org_filters = frappe._dict(filters)

    # Obtener los datos del Balance Sheet según los filtros
    balance_sheet_data = get_balance_sheet_data(org_filters)

    # Definir el nombre basado en la cuenta, party o compañía
    account_name = filters.get("account")[0] if filters.get("account") else filters.get("party_name", "")
    company_name = filters.get("company", "")

    # Obtener fecha de hoy
    today_date = datetime.date.today().strftime("%d/%m/%Y")

    # Formatear periodo
    from_date = datetime.datetime.strptime(filters.get("period_start_date"), "%Y-%m-%d").strftime("%d-%b")
    to_date = datetime.datetime.strptime(filters.get("period_end_date"), "%Y-%m-%d").strftime("%d-%b del %Y")
    formatted_today = datetime.datetime.strptime(today_date, "%d/%m/%Y").strftime("%d-%b del %Y")
    formatted_period = f"De {from_date} a {to_date}"
    year = datetime.datetime.strptime(today_date, "%d/%m/%Y").year

    balance_sheet_skeleton = [{
        "parent": "ACTIVO",
        "ol": "A",
        "title_format": "h3",
        "children": [
            {
                "parent": "ACTIVO NO CORRIENTE",
                "ol": "I",
                "title_format": "b",
                "children": [
                    {
                        "parent": "Inmovilizado intangible.",
                        "ol": "1",
                        "children": [
                            {"parent": "Desarrollo.", "accounts": (201, "2801", "2901")},
                            {"parent": "Concesiones.", "accounts": (202, "2802", "2902")},
                            {"parent": "Patentes, licencias, marcas y similares.", "accounts": (203, "2803", "2903")},
                            {"parent": "Fondos de comercio.", "accounts": (204, "2804")},
                            {"parent": "Aplicaciones informáticas.", "accounts": (206, "2806", "2906")},
                            {"parent": "Otro inmovilizado intangible.", "accounts": (205, 209, "2805", "2905")}
                        ]
                    },
                    {
                        "parent": "Inmovilizado material.",
                        "ol": "1",
                        "children": [
                            {"parent": "Terrenos y construcciones.", "accounts": (210, 211, "2811", "2910", "2911")},
                            {
                                "parent": "Instalaciones técnicas, y otro inmovilizado material.",
                                "accounts": (
                                    212, 213, 214, 215, 216, 217, 218, 219, "2812", "2813", "2814", "2815", "2816",
                                    "2817", "2818", "2819", "2912", "2913", "2914", "2915", "2916", "2917", "2918",
                                    "2919"
                                )
                            },
                            {"parent": "Inmovilizado en curso y anticipos.", "accounts": (23, )}
                        ]
                    },
                    {
                        "parent": "Inversiones inmobiliarias.",
                        "ol": "1",
                        "children": [
                            {"parent": "Terrenos.", "accounts": (220, "2920")},
                            {"parent": "Construcciones.", "accounts": (221, "282", "2921")}
                        ]
                    },
                    {
                        "parent": "Inversiones en empresas del grupo y asociadas a largo plazo.",
                        "ol": "1",
                        "children": [
                            {
                                "parent": "Instrumentos de patrimonio.",
                                "accounts": (
                                    2403, 2404, "2493", "2494", "2933", "2934"
                                )
                            },
                            {"parent": "Créditos a empresas.", "accounts": (2423, 2424, "2953", "2954")},
                            {"parent": "Valores representativos de deuda.", "accounts": (2413, 2414, "2943", "2944")},
                            {"parent": "Derivados.", "accounts": tuple()},
                            {"parent": "Otros activos financieros.", "accounts": tuple()}
                        ]
                    },
                    {
                        "parent": "Inversiones financieras a largo plazo.",
                        "ol": "1",
                        "children": [
                            {
                                "parent": "Instrumentos de patrimonio.",
                                "accounts": (2405, "2495", 250, "259", "2935", "2936")
                            },
                            {"parent": "Créditos a terceros.", "accounts": (2425, 252, 253, 254, "2955", "298")},
                            {"parent": "Valores representativos de deuda.", "accounts": (2415, 251, "2945", "297")},
                            {"parent": "Derivados.", "accounts": (255, )},
                            {"parent": "Otros activos financieros.", "accounts": (258, 26)}
                        ]
                    },
                    {
                        "parent": "Activos por impuesto diferido.",
                        "accounts": (474, )
                    }
                ]
            },
            {
                "parent": "ACTIVO CORRIENTE",
                "ol": "I",
                "title_format": "b",
                "children": [
                    {
                        "parent": "Activos no corrientes mantenidos para la venta.",
                        "accounts": (580, 581, 582, 583, 584, "599")
                    },
                    {
                        "parent": "Existencias.",
                        "ol": "1",
                        "children": [
                            {"parent": "Comerciales.", "accounts": (30, "390")},
                            {
                                "parent": "Materias primas y otros aprovisionamientos.",
                                "accounts": (31, 32, "391", "392")
                            },
                            {"parent": "Productos en curso.", "accounts": (33, 34, "393", "394")},
                            {"parent": "Productos terminados.", "accounts": (35, "395")},
                            {"parent": "Subproductos, residuos y materiales recuperados.", "accounts": (36, "396")},
                            {"parent": "Anticipos a proveedores", "accounts": (407, )}
                        ]
                    },{
                        "parent": "Deudores comerciales y otras cuentas a cobrar.",
                        "ol": "1",
                        "children": [
                            {
                                "parent": "Clientes por ventas y prestaciones de servicios.",
                                "accounts": (430, 431, 432, 435, 436, "437", "490", "4935")},
                            {
                                "parent": "Clientes, empresas del grupo y asociadas.",
                                "accounts": (433, 434, "4933", "4934")
                            },
                            {"parent": "Deudores varios.", "accounts": (44,)},
                            {"parent": "Personal", "accounts": (460, 544)},
                            {"parent": "Activos por impuesto corriente.", "accounts": (4709, )},
                            {
                                "parent": "Otros créditos con las Administraciones Públicas.",
                                "accounts": (4700, 4708, 471, 472)
                            },
                            {"parent": "Accionistas (socios) por desembolsos exigidos.", "accounts": (5580, )},
                        ]
                    },
                    {
                        "parent": "Inversiones en empresas del grupo y asociadas a corto plazo.",
                        "ol": "1",
                        "children": [
                            {
                                "parent": "Instrumentos de patrimonio.",
                                "accounts": (5303, 5304, "5393", "5394", "5933", "5934")
                            },
                            {"parent": "Créditos a empresas.", "accounts": (5323, 5324, 5343, 5344, "5953", "5954")},
                            {
                                "parent": "Valores representativos de deuda.",
                                "accounts": (5313, 5314, 5333, 5334, "5943", "5944")
                            },
                            {"parent": "Derivados.",  "accounts": tuple()},
                            {"parent": "Otros activos financieros.",  "accounts": (5353, 5354, 5523, 5524)},
                        ]
                    },
                    {
                        "parent": "Inversiones financieras a corto plazo.",
                        "ol": "1",
                        "children": [
                            {
                                "parent": "Instrumentos del patrimonio.",
                                "accounts": (5305, 540, "5395", "549", "5935", "5936")
                            },
                            {"parent": "Créditos a empresas.", "accounts": (5325, 5345, 542, 543, 547, "5955", "598")},
                            {
                                "parent": "Valores representativos de deuda.",
                                "accounts": (5315, 5335, 541, 546, "5945", "597")
                            },
                            {"parent": "Derivados.", "accounts": (5590, 5593)},
                            {"parent": "Otros activos financieros.", "accounts": (5355, 545, 548, 551, 5525, 565, 566)},
                        ]
                    },
                    {
                        "parent": "Periodificaciones a corto plazo.", "accounts": (480, 567)
                    },
                    {
                        "parent": "Efectivo y otros activos líquidos equivalentes.",
                        "ol": "1",
                        "children": [
                            {"parent": "Tesorería.", "accounts": (570, 571, 572, 573, 574, 575)},
                            {"parent": "Otros activos líquidos equivalentes.", "accounts": (576, )}
                        ]
                    }
                ]
            }
        ]
    },
    {
        "parent": "PATRIMONIO NETO Y PASIVO",
        "title_format": "h3",
        "ol": "A",
        "children": [
            {
                "parent": "PATRIMONIO NETO",
                "title_format": "b",
                "ol": "custom",
                "children": [
                    {
                        "parent": "A-1) Fondos propios.",
                        "ol": "I",
                        "title_format": "b",
                        "children": [
                            {
                                "parent": "Capital",
                                "children": [
                                    {"parent": "Capital escriturado", "accounts": (100, 101, 102)},
                                    {"parent": "(Capital no exigido)", "accounts": ("1030", "1040")},
                                ]
                            },
                            {
                                "parent": "Prima de emisión",
                                "accounts": (110, )
                            },
                            {
                                "parent": "Reservas",
                                "children": [
                                    {"parent": "Legal y estatutarias.", "accounts": (112, 1141)},
                                    {"parent": "Otras reservas.", "accounts": (113, 1140, 1142, 1143, 1144, 115, 119)},
                                ]
                            },
                            {
                                "parent": "(Acciones y participaciones en patrimonio propias).",
                                "accounts": ("108", "109")
                            },
                            {
                                "parent": "Resultados de ejercicios anteriores.",
                                "children": [
                                    {"parent": "Remanente.", "accounts": (120, )},
                                    {"parent":  "(Resultados negativos de ejercicios anteriores)", "accounts": ("121", )}
                                ]
                            },
                            {
                                "parent": "Otras aportaciones de socios.",
                                "accounts": (118, )
                            },
                            {
                                "parent": "Resultado del ejercicio.",
                                "accounts": (129, )
                            },
                            {
                                "parent": "(Dividendo a cuenta).",
                                "accounts": ("557", )
                            },
                            {
                                "parent": "Otros instrumentos de patrimonio neto.",
                                "accounts": (111, )
                            },
                        ]
                    },
                    {
                        "parent": "A-2) Ajustes por cambios de valor.",
                        "ol": "I",
                        "title_format": "b",
                        "children": [
                            {
                                "parent": "Activos financieros a valor razonable con cambios en el patrimonio neto.",
                                "accounts": (133, )
                            },
                            {
                                "parent": "Operaciones de cobertura.",
                                "accounts": (1340, )
                            },
                            {
                                "parent": "Otros.",
                                "accounts": (137, )
                            },
                        ]
                    },
                    {
                        "parent": "A-3) Subvenciones, donaciones y legados recibidos.",
                        "accounts": (130, 131, 132)
                    }
                ]
            },
            {
                "parent": "PASIVO NO CORRIENTE",
                "title_format": "b",
                "ol": "I",
                "children": [
                    {
                        "parent": "Provisiones a largo plazo",
                        "ol": "1",
                        "children": [
                            {"parent": "Obligaciones por prestaciones a largo plazo al personal.", "accounts": (140, )},
                            {"parent": "Actuaciones medioambientales.", "accounts": (145, )},
                            {"parent": "Provisiones por reestructuración", "accounts": (146, )},
                            {"parent": "Otras provisiones", "accounts": (141, 142, 143, 147)},
                        ]
                    },
                    {
                        "parent": "Deudas a largo plazo.", "children": [
                            {"parent": "Obligaciones y otros valores negociables.", "accounts": (177, 178, 179)},
                            {"parent": "Deudas con entidades de crédito.", "accounts": (1605, 170)},
                            {"parent": "Acreedores por arrendamiento financiero.", "accounts": (1625, 174)},
                            {"parent": "Derivados.", "accounts": (176, )},
                            {"parent": "Otros pasivos financieros.", "accounts": (1615,1635,171,172,173,175,180,185,189)}
                        ]
                    },
                    {
                        "parent": "Deudas con empresas del grupo y asociadas a largo plazo.",
                        "accounts": (1603,1604,1613,1614,1623,1624,1633,1634)
                    },
                    {
                        "parent": "Pasivos por impuesto diferido.", "accounts": (479, )
                    },
                    {
                        "parent": "Periodificaciones a largo plazo.", "accounts": (181, )
                    },
                ]
            },
            {
                "parent": "PASIVO CORRIENTE",
                "title_format": "b",
                "ol": "I",
                "children": [
                    {
                        "parent": "Pasivos vinculados con activos no corrientes mantenidos para la venta.",
                        "accounts": (585, 586, 587, 588, 589)
                    },
                    {"parent": "Provisiones a corto plazo.", "accounts": (499, 529)},
                    {
                        "parent": "Deudas a corto plazo.", "children": [
                            {"parent": "Obligaciones y otros valores negociables.", "accounts": (500, 501, 505, 506)},
                            {"parent": "Deudas con entidades de crédito.", "accounts": (5105, 520, 527)},
                            {"parent": "Acreedores por arrendamiento financiero.", "accounts": (5125, 524)},
                            {"parent": "Derivados.", "accounts": (5595, 5598)},
                            {
                                "parent": "Otros pasivos financieros.",
                                "accounts": (
                                    "1034", "1044", "190", "192", 194, 509, 5115, 5135, 5145, 521, 522, 523, 525, 526,
                                    528, 551, 5525, 555, 5565, 5566, 560, 561, 569
                                )
                            },
                        ]
                    },
                    {
                        "parent": "Deudas con empresas del grupo y asociadas a corto plazo.",
                        "accounts": (5103, 5104, 5113, 5114, 5123, 5124, 5133, 5134, 5143, 5144, 5523, 5524, 5563, 5564)
                    },
                    {
                        "parent": "Acreedores comerciales y otras cuentas a pagar.",
                        "children": [
                            {"parent": "Proveedores.", "accounts": (400, 401, 405, "406")},
                            {
                                "parent": "Proveedores, empresas del grupo y asociadas",
                                "accounts": (403, 404)
                            },
                            {"parent": "Acreedores varios.", "accounts": (41, )},
                            {"parent": "Personal (remuneraciones pendientes de pago).", "accounts": (465, 466)},
                            {"parent": "Pasivos por impuesto corriente.", "accounts": (4752, )},
                            {
                                "parent": "Otras deudas con las Administraciones Públicas.",
                                "accounts": (4750, 4751, 4758, 476, 477)
                            },
                            {
                                "parent": "Anticipos de clientes.",
                                "accounts": (438, )
                            }
                        ]
                    },
                    {
                        "parent": "Periodificaciones a corto plazo", "accounts": (485, 568)
                    }
                ]
            }
        ]
    }]

    set_accounts(balance_sheet_skeleton, balance_sheet_data)
    calculate_totals(balance_sheet_skeleton)

    if format == "PDF":
        # Contenido del encabezado directamente en el .py
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
                    font-size: 14px;
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
                    font-size: 10px;
                    text-transform: uppercase;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Balance de Situación</h1>
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
        """
        def account_div(account): 
            return f"""
            <table style="width:100%;" class="account">
                <td>{account["account"]}</td>
                <td style="text-align: right;">{decimal(account["balance"])}</td>
            </table>
            """

        def title_div(title):
            return f"""
            <div style="width: 100%; margin-bottom: 10px; margin-top: 10px; font-size: 10.5px;">
                <span>
                {title["parent"]}
                </span>
                <span style="float: right; padding-left: 10px;">{decimal(title["total"]) if "total" in title else decimal(0.00)}</span>
            </div>
            """

        def accounts_html(balance_structure, ol_format, title_format):
            nonlocal body_html


            if ol_format != "custom":
                body_html += f"""
                <ol {f"type={ol_format}"}>
                """

            for parent in balance_structure:
                if parent["total"]:
                    if title_format:
                        body_html += f"<{title_format}>"

                    if ol_format != "custom":
                        body_html += """
                        <li>
                        """

                    body_html += title_div(parent)

                    if title_format:
                        body_html += f"</{title_format}>"

                    if has_accounts(parent):
                        for account in parent["accounts"]:
                            body_html += account_div(account)

                    elif has_children(parent):
                        accounts_html(
                            parent["children"],
                            parent["ol"] if "ol" in parent else None,
                            parent["title_format"] if "title_format" in parent else None
                        )
                    if ol_format != "custom":
                        body_html += """
                            </li>
                        """

            if ol_format != "custom":
                body_html += """
                </ol>
                """


        # Añadir las entradas de la tabla
        total_balance = 0
        for main_title in balance_sheet_skeleton:
            body_html += f"""
            <div class="observations">{main_title["parent"]}</div>
                <div style="width:95%;">
            """
            accounts_html(main_title["children"], main_title["ol"], main_title["title_format"])
            body_html += "</div>"

            body_html += f"""
                <div class="total">
                    <table style="width:92.5%; margin-left: auto; margin-right: auto;">
                        <tr>
                            <td><b>TOTAL {main_title["parent"]}</b></td>
                            <td style="text-align: right;"><b>{decimal(main_title["total"])}</b></td>
                        </tr>
                    </table>
                </div>
            """

        # # Combinar el contenido del encabezado y el cuerpo
        html_content = header_html + body_html

        # Generar el archivo PDF
        pdf_content = get_pdf(html_content, {
            "header-spacing": 5,
            "footer-right": "Página: [page] de [toPage]",
        })

        # Generar nombre del archivo PDF
        file_name = "Hoja_Balance.pdf"
        file_path = os.path.join(frappe.utils.get_site_path(), 'private', 'files', file_name)

        # Guardar el archivo PDF
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "is_private": 1,
            "content": pdf_content
        })
        file_doc.save(ignore_permissions=True)

        return file_doc.file_url
