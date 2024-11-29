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
def account_div(account):
    return f"""
    <table class="account">
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

def accounts_html(balance_structure, title_format, body_html):
    body_html += """<div class="container">"""

    for parent in balance_structure:
        if parent.get("total"):
            if title_format:
                body_html += f"<{title_format}>"

            body_html += title_div(parent)

            if title_format:
                body_html += f"</{title_format}>"

            if has_accounts(parent):
                if parent["parent"] == "VII. Resultado del ejercicio.":
                    body_html += account_div({"account": "129 - Resultado del ejercicio", "balance": parent["total"]})
                else:
                    for account in parent["accounts"]:
                        body_html += account_div(account)

            elif has_children(parent):
                body_html = accounts_html(
                    parent["children"],
                    parent.get("title_format"),
                    body_html
                )

    body_html += "</div>"

    return body_html

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

            parent.update({"accounts": parent_accounts, "total": balance_total})

        elif has_children(parent):
            set_accounts(parent["children"], balance_sheet_data)

def calculate_totals(balance_structure):
    for parent in balance_structure:
        if parent["parent"] == "5. Otros pasivos financieros.":
            total = 0
            new_accounts = []

            for account in parent["accounts"]:
                new_accounts.append(account.copy())

            for account in new_accounts:
                if account["balance_pasivo"]:
                    account.update({"balance": account["balance_pasivo"]})

                total += account["balance"]

            parent["accounts"] = new_accounts
                # if account["balance_pasivo"]:
                #     account.update({"balance": account["balance_pasivo"], "time":datetime.datetime.now()}) 

                #     total += account["balance"]

            parent["total"] = total

        if 'children' in parent:
            calculate_totals(parent['children'])

            total = sum(child.get('total', 0) for child in parent['children'] if 'total' in child)
            parent['total'] = total

# Función auxiliar para obtener los datos del General Ledger
def get_balance_sheet_data(filters):
    # HACK Lógica de datos anterior

    # period_list = get_period_list(
    #     filters.from_fiscal_year, filters.to_fiscal_year, filters.period_start_date, filters.period_end_date,
    #     filters.filter_based_on, filters.periodicity, company=filters.company,
	# )

    # filters.period_start_date = period_list[0]["year_start_date"]

    # asset = get_data(
    #     filters.company, "Asset", "Debit", period_list, only_current_fiscal_year=False, filters=filters,
    #     accumulated_values=filters.accumulated_values,
	# )

    # liability = get_data(
	# 	filters.company, "Liability", "Credit", period_list, only_current_fiscal_year=False, filters=filters,
	# 	accumulated_values=filters.accumulated_values,
	# )

    # equity = get_data(
	# 	filters.company, "Equity", "Credit", period_list, only_current_fiscal_year=False, filters=filters,
	# 	accumulated_values=filters.accumulated_values,
	# )

    # data = []
    # data.extend(asset or [])
    # data.extend(liability or [])
    # data.extend(equity or [])

    # data = sorted(
    #     [{"balance": e["total"], "account": e["account"], "account_number": 0} for e in data if e],
    #     key=lambda a: a["account"]
    # )

    # # Búsqueda de número de cuenta con query
    # account_query = f"""
    # SELECT account_number, name
    # FROM `tabAccount`
    # WHERE company = "{filters.company}"
    # ORDER BY account_number
    # """

    # tabAccounts = frappe.db.sql(account_query, as_dict=True)

    # for entry in data:
    #     account_number = list(filter(lambda a: a["name"] == entry["account"], tabAccounts))

    #     if len(account_number):
    #         entry.update({"account_number": account_number[0]["account_number"]})

    # HACK Lógica de datos temporal
    acc_query = f"""
    SELECT
        account_number, name, lft, rgt
    FROM
        `tabAccount`
    WHERE
        company = "{filters.company}" AND report_type IN ("Balance Sheet", "Profit and Loss")
    ORDER BY account_number
    """

    Accounts = frappe.db.sql(acc_query, as_dict=True)

    gl_query = f"""
    SELECT
        account.name, (SUM(gl_entry.debit) - SUM(gl_entry.credit)) AS balance, account.lft, parent.account_number
    FROM
        `tabGL Entry` gl_entry
    LEFT JOIN
        `tabAccount` account ON account.name = gl_entry.account
    LEFT JOIN
        `tabAccount` parent ON parent.name = account.parent_account
    WHERE
        gl_entry.company = "{filters.company}"
        AND account.company = "{filters.company}"
        AND account.report_type IN ("Balance Sheet", "Profit and Loss")
        AND gl_entry.posting_date >= "{filters.period_start_date}"
        AND gl_entry.posting_date <= "{filters.period_end_date}"
        AND account.account_number != 551
        AND parent.account_number != 551
    GROUP BY account.name
    """

    GLEntries = frappe.db.sql(gl_query, as_dict=True)

    pasivo_activo = list(filter(lambda a: a["account_number"] == "551", Accounts))

    if len(pasivo_activo):
        activo_query = f"""
        SELECT
            SUM(gl_entry.debit) - SUM(gl_entry.credit) AS balance
        FROM
            `tabGL Entry` gl_entry
        LEFT JOIN
            `tabAccount` account ON account.name = gl_entry.account
        LEFT JOIN
            `tabAccount` parent ON parent.name = account.parent_account
        WHERE
            gl_entry.company = "{filters.company}"
            AND gl_entry.posting_date >= "{filters.period_start_date}"
            AND gl_entry.posting_date <= "{filters.period_end_date}"
            AND parent.account_number = 551
            AND account.account_number IN (551000600)
        """
        pasivo_query = f"""
        SELECT
            SUM(gl_entry.credit) - SUM(gl_entry.debit) AS balance
        FROM
            `tabGL Entry` gl_entry
        LEFT JOIN
            `tabAccount` account ON account.name = gl_entry.account
        LEFT JOIN
            `tabAccount` parent ON parent.name = account.parent_account
        WHERE
            gl_entry.company = "{filters.company}"
            AND gl_entry.posting_date >= "{filters.period_start_date}"
            AND gl_entry.posting_date <= "{filters.period_end_date}"
            AND parent.account_number = 551
            AND account.account_number IN (551000000,551000001,551000900)
        """
        activo_total = frappe.db.sql(activo_query, as_dict=True)
        pasivo_total = frappe.db.sql(pasivo_query, as_dict=True)

        if len(activo_total) and len(pasivo_total):
            GLEntries.append({
                "lft": pasivo_activo[0]["lft"] + 5,
                "balance": activo_total[0]["balance"],
                "balance_pasivo": pasivo_total[0]["balance"]
            })

    data = []

    for entry in Accounts:
        account_gl_entries = list(filter(lambda gl: gl["lft"] >= entry["lft"] and gl["lft"] <= entry["rgt"], GLEntries))
        
        if account_gl_entries:
            data.append({
                "balance": sum(a["balance"] or 0 for a in account_gl_entries),
                "balance_pasivo": sum(a["balance_pasivo"] or 0 for a in account_gl_entries if a.get("balance_pasivo")),
                "account": entry["name"],
                "account_number": entry["account_number"]
            })

    return data

def filter_accounts(account_numbers, balance_data):
    activo_pasivo = ("551", )
    # activo_pasivo_entries = list(filter(lambda a: a in activo_pasivo, account_numbers))
    # activo_pasivo_gle = None

    # if len(activo_pasivo_entries):
    #     for entry in activo_pasivo_entries:
    #         gle = list(filter(
    #             lambda bd: bd["account_number"] == entry.removesuffix("a").removesuffix("p"),
    #             sorted(balance_data, key=lambda bd: int(bd["account_number"]))
    #         ))

    #         if len(gle):
    #             if entry.endswith("p"):
    #                 gle[0]["balance"] = gle[0]["balance_pasivo"]

            # activo_pasivo_gle = gle[0]

    indistinct_accounts = list(filter(
        lambda an: type(an) == str and an.endswith("*") and an not in activo_pasivo,
        account_numbers
    ))
    negative_accounts = list(filter(
        lambda an: type(an) == str and an not in indistinct_accounts and an not in activo_pasivo,
        account_numbers
    ))
    account_numbers = list(map(
        lambda a: int(str(a).removesuffix("*")),
        list(filter(lambda an: an not in activo_pasivo, account_numbers))
    ))

    res = list(filter(
        lambda bd: int(bd["account_number"]) in account_numbers,
        sorted(balance_data, key=lambda bd: int(bd["account_number"]))
    ))

    for entry in res:
        if str(entry["account_number"]) in negative_accounts:
            if entry["balance"] > 0:
                entry["balance"] = -entry["balance"]

        elif str(entry["account_number"]) + "*" not in indistinct_accounts:
            entry["balance"] = abs(entry["balance"])

    return res

def decimal(number):
    return format_decimal(round(number, 2), "#,###.00##", locale="es_ES")

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
        "title_format": "h3",
        "children": [
            {
                "parent": "A) ACTIVO NO CORRIENTE",
                "title_format": "b",
                "children": [
                    {
                        "parent": "I. Inmovilizado intangible.",
                        "children": [
                            {"parent": "1. Desarrollo.", "accounts": (201, "2801", "2901")},
                            {"parent": "2. Concesiones.", "accounts": (202, "2802", "2902")},
                            {"parent": "3. Patentes, licencias, marcas y similares.", "accounts": (203, "2803", "2903")},
                            {"parent": "4. Fondos de comercio.", "accounts": (204, "2804")},
                            {"parent": "5. Aplicaciones informáticas.", "accounts": (206, "2806", "2906")},
                            {"parent": "6. Otro inmovilizado intangible.", "accounts": (205, 209, "2805", "2905")}
                        ]
                    },
                    {
                        "parent": "II. Inmovilizado material.",
                        "children": [
                            {"parent": "1. Terrenos y construcciones.", "accounts": (210, 211, "2811", "2910", "2911")},
                            {
                                "parent": "2. Instalaciones técnicas, y otro inmovilizado material.",
                                "accounts": (
                                    212, 213, 214, 215, 216, 217, 218, 219, "2812", "2813", "2814", "2815", "2816",
                                    "2817", "2818", "2819", "2912", "2913", "2914", "2915", "2916", "2917", "2918",
                                    "2919"
                                )
                            },
                            {"parent": "3. Inmovilizado en curso y anticipos.", "accounts": (23, )}
                        ]
                    },
                    {
                        "parent": "III. Inversiones inmobiliarias.",
                        "children": [
                            {"parent": "1. Terrenos.", "accounts": (220, "2920")},
                            {"parent": "2. Construcciones.", "accounts": (221, "282", "2921")}
                        ]
                    },
                    {
                        "parent": "IV. Inversiones en empresas del grupo y asociadas a largo plazo.",
                        "children": [
                            {
                                "parent": "1. Instrumentos de patrimonio.",
                                "accounts": (
                                    2403, 2404, "2493", "2494", "2933", "2934"
                                )
                            },
                            {"parent": "2. Créditos a empresas.", "accounts": (2423, 2424, "2953", "2954")},
                            {"parent": "3. Valores representativos de deuda.", "accounts": (2413, 2414, "2943", "2944")},
                            {"parent": "4. Derivados.", "accounts": tuple()},
                            {"parent": "5. Otros activos financieros.", "accounts": tuple()}
                        ]
                    },
                    {
                        "parent": "V. Inversiones financieras a largo plazo.",
                        "children": [
                            {
                                "parent": "1. Instrumentos de patrimonio.",
                                "accounts": (2405, "2495", 250, "259", "2935", "2936")
                            },
                            {"parent": "2. Créditos a terceros.", "accounts": (2425, 252, 253, 254, "2955", "298")},
                            {"parent": "3. Valores representativos de deuda.", "accounts": (2415, 251, "2945", "297")},
                            {"parent": "4. Derivados.", "accounts": (255, )},
                            {"parent": "5. Otros activos financieros.", "accounts": (258, 26)}
                        ]
                    },
                    {
                        "parent": "VI. Activos por impuesto diferido.",
                        "accounts": (474, )
                    }
                ]
            },
            {
                "parent": "B) ACTIVO CORRIENTE",
                "title_format": "b",
                "children": [
                    {
                        "parent": "I. Activos no corrientes mantenidos para la venta.",
                        "accounts": (580, 581, 582, 583, 584, "599")
                    },
                    {
                        "parent": "II. Existencias.",
                        "children": [
                            {"parent": "1. Comerciales.", "accounts": (30, "390")},
                            {
                                "parent": "2. Materias primas y otros aprovisionamientos.",
                                "accounts": (31, 32, "391", "392")
                            },
                            {"parent": "3. Productos en curso.", "accounts": (33, 34, "393", "394")},
                            {"parent": "4. Productos terminados.", "accounts": (35, "395")},
                            {"parent": "5. Subproductos, residuos y materiales recuperados.", "accounts": (36, "396")},
                            {"parent": "6. Anticipos a proveedores", "accounts": (407, )}
                        ]
                    },{
                        "parent": "III. Deudores comerciales y otras cuentas a cobrar.",
                        "children": [
                            {
                                "parent": "1. Clientes por ventas y prestaciones de servicios.",
                                "accounts": (430, 431, 432, 435, 436, "437", "490", "4935")},
                            {
                                "parent": "2. Clientes, empresas del grupo y asociadas.",
                                "accounts": (433, 434, "4933", "4934")
                            },
                            {"parent": "3. Deudores varios.", "accounts": (44,)},
                            {"parent": "4. Personal", "accounts": ("460*", 544)},
                            {"parent": "5. Activos por impuesto corriente.", "accounts": (4709, )},
                            {
                                "parent": "6. Otros créditos con las Administraciones Públicas.",
                                "accounts": (4700, 4708, "471*", 472, "473*")
                            },
                            {"parent": "7. Accionistas (socios) por desembolsos exigidos.", "accounts": (5580, )},
                        ]
                    },
                    {
                        "parent": "IV. Inversiones en empresas del grupo y asociadas a corto plazo.",
                        "children": [
                            {
                                "parent": "1. Instrumentos de patrimonio.",
                                "accounts": (5303, 5304, "5393", "5394", "5933", "5934")
                            },
                            {"parent": "2. Créditos a empresas.", "accounts": (5343, 5344, "5953", "5954", 532)},
                            {
                                "parent": "3. Valores representativos de deuda.",
                                "accounts": (5313, 5314, 5333, 5334, "5943", "5944")
                            },
                            {"parent": "4. Derivados.",  "accounts": tuple()},
                            {"parent": "5. Otros activos financieros.",  "accounts": (5353, 5354, 5523, 5524)},
                        ]
                    },
                    {
                        "parent": "V. Inversiones financieras a corto plazo.",
                        "children": [
                            {
                                "parent": "1. Instrumentos del patrimonio.",
                                "accounts": (5305, 540, "5395", "549", "5935", "5936")
                            },
                            {"parent": "2, Créditos a empresas.", "accounts": (5345, 542, 543, "547*", "5955", "598")},
                            {
                                "parent": "3. Valores representativos de deuda.",
                                "accounts": (5315, 5335, 541, 546, "5945", "597")
                            },
                            {"parent": "4. Derivados.", "accounts": (5590, 5593)},
                            {"parent": "5. Otros activos financieros.", "accounts": (5355, 545, 548, 5525, 565, 566, 551)},
                        ]
                    },
                    {
                        "parent": "VI. Periodificaciones a corto plazo.", "accounts": (480, 567)
                    },
                    {
                        "parent": "VII. Efectivo y otros activos líquidos equivalentes.",
                        "children": [
                            {"parent": "1. Tesorería.", "accounts": (570, 571, "572*", 573, 574, 575)},
                            {"parent": "2. Otros activos líquidos equivalentes.", "accounts": (576, )}
                        ]
                    }
                ]
            }
        ]
    },
    {
        "parent": "PATRIMONIO NETO Y PASIVO",
        "title_format": "h3",
        "children": [
            {
                "parent": "A) PATRIMONIO NETO",
                "title_format": "b",
                "children": [
                    {
                        "parent": "A-1) Fondos propios.",
                        "title_format": "b",
                        "children": [
                            {
                                "parent": "I. Capital.",
                                "children": [
                                    {"parent": "1. Capital escriturado.", "accounts": (100, 101, 102)},
                                    {"parent": "2. (Capital no exigido).", "accounts": ("1030", "1040")},
                                ]
                            },
                            {
                                "parent": "II. Prima de emisión",
                                "accounts": (110, )
                            },
                            {
                                "parent": "III. Reservas",
                                "children": [
                                    {"parent": "1. Legal y estatutarias.", "accounts": (112, 1141)},
                                    {"parent": "2. Otras reservas.", "accounts": (113, 1140, 1142, 1143, 1144, 115, 119)},
                                ]
                            },
                            {
                                "parent": "IV. (Acciones y participaciones en patrimonio propias).",
                                "accounts": ("108", "109")
                            },
                            {
                                "parent": "V. Resultados de ejercicios anteriores.",
                                "children": [
                                    {"parent": "1. Remanente.", "accounts": (120, )},
                                    {"parent":  "2. (Resultados negativos de ejercicios anteriores)", "accounts": ("121", )}
                                ]
                            },
                            {
                                "parent": "VI. Otras aportaciones de socios.",
                                "accounts": ("118", )
                            },
                            {
                                "parent": "VII. Resultado del ejercicio.",
                                # HACK puestas todas las cuentas de PYG hasta conseguir una forma prolija de traspasar
                                # los saldos de las cuentas de otros reportes
                                "accounts": (
                                    700,701,702,703,704,"706","708","709", 705, "6930", "71*", 7930, 73, "600", 6060,
                                    6090, 6080, "610*","601", "602", 6061, 6062, 6081, 6082, 6091, 6092, "611*", "612*",
                                    "607", "6931", "6932", "6933", 7931, 7932, 7933, 75, 740, 747,"640","641","6450",
                                    "642","643","649","644", "6457", 7950, 7957, "62", "631", "634", 636, 639, "650",
                                    "694", "695", 794, 7954, "651", "659", "68",746,7951, 7952, 7955, 7956, "690","691",
                                    "692", 790, 791, 792, "670", "671", "672", 770, 771, 772,"678" ,778, "6300*",
                                    "6301*", "633", 638,7600, 7601,7602, 7603,7610, 7611, 76200, 76201, 76210, 76211,
                                    7612, 7613, 76202, 76203, 76212, 76213, 767, 769, "662","6610", "6611", "6615",
                                    "6616", "6640", "6641", "6650", "6651", "6654", "6655", "6612", "6613", "6617",
                                    "6618", "6642", "6643", "6652", "6653", "6656", "6657", "669", "660", "6630",
                                    "6631", "6633", "6634", 7630, 7631, 7633, 7634, "6632",7632, "668", 768, "696",
                                    "697", "698", "699", 796, 797, 798, 799, "666", "667", "673", "675", 766, 773, 775,
                                    "6300*", "6301*", "633" ,638
                               )
                            },
                            {
                                "parent": "VIII. (Dividendo a cuenta).",
                                "accounts": ("557", )
                            },
                            {
                                "parent": "IX. Otros instrumentos de patrimonio neto.",
                                "accounts": (111, )
                            },
                        ]
                    },
                    {
                        "parent": "A-2) Ajustes por cambios de valor.",
                        "title_format": "b",
                        "children": [
                            {
                                "parent": "I. Activos financieros a valor razonable con cambios en el patrimonio neto.",
                                "accounts": (133, )
                            },
                            {
                                "parent": "II. Operaciones de cobertura.",
                                "accounts": (1340, )
                            },
                            {
                                "parent": "III. Otros.",
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
                "parent": "B) PASIVO NO CORRIENTE",
                "title_format": "b",
                "children": [
                    {
                        "parent": "I. Provisiones a largo plazo",
                        "children": [
                            {"parent": "1. Obligaciones por prestaciones a largo plazo al personal.", "accounts": (140, )},
                            {"parent": "2. Actuaciones medioambientales.", "accounts": (145, )},
                            {"parent": "3. Provisiones por reestructuración", "accounts": (146, )},
                            {"parent": "4. Otras provisiones", "accounts": (141, 142, 143, 147)},
                        ]
                    },
                    {
                        "parent": "II. Deudas a largo plazo.", "children": [
                            {"parent": "1. Obligaciones y otros valores negociables.", "accounts": (177, 178, 179)},
                            {"parent": "2. Deudas con entidades de crédito.", "accounts": (1605, 170)},
                            {"parent": "3. Acreedores por arrendamiento financiero.", "accounts": (1625, 174)},
                            {"parent": "4. Derivados.", "accounts": (176, )},
                            {"parent": "5. Otros pasivos financieros.", "accounts": (1615,1635,171,172,173,175,180,185,189)}
                        ]
                    },
                    {
                        "parent": "III. Deudas con empresas del grupo y asociadas a largo plazo.",
                        "accounts": (1603,1604,1613,1614,1623,1624,1633,1634)
                    },
                    {
                        "parent": "IV. Pasivos por impuesto diferido.", "accounts": (479, )
                    },
                    {
                        "parent": "V. Periodificaciones a largo plazo.", "accounts": (181, )
                    },
                ]
            },
            {
                "parent": "C) PASIVO CORRIENTE",
                "title_format": "b",
                "children": [
                    {
                        "parent": "I. Pasivos vinculados con activos no corrientes mantenidos para la venta.",
                        "accounts": (585, 586, 587, 588, 589)
                    },
                    {"parent": "II. Provisiones a corto plazo.", "accounts": (499, 529)},
                    {
                        "parent": "III. Deudas a corto plazo.", "children": [
                            {"parent": "1.Obligaciones y otros valores negociables.", "accounts": (500, 501, 505, 506)},
                            {"parent": "2. Deudas con entidades de crédito.", "accounts": (5105, 520, 527)},
                            {"parent": "3. Acreedores por arrendamiento financiero.", "accounts": (5125, 524)},
                            {"parent": "4. Derivados.", "accounts": (5595, 5598)},
                            {
                                "parent": "5. Otros pasivos financieros.",
                                "accounts": (
                                    "1034", "1044", "190", "192", 194, 509, 5115, 5135, 5145, 521, 522, 523, 525, "526",
                                    528, 5525, "555", 551, 5565, 5566, 560, 561, 569
                                )
                            },
                        ]
                    },
                    {
                        "parent": "IV. Deudas con empresas del grupo y asociadas a corto plazo.",
                        "accounts": (5103, 5104, 5113, 5114, 5123, 5124, 5133, 5134, 5143, 5144, 552, 5563, 5564)
                    },
                    {
                        "parent": "V. Acreedores comerciales y otras cuentas a pagar.",
                        "children": [
                            {"parent": "1. Proveedores.", "accounts": (400, 401, 405, "406")},
                            {
                                "parent": "2. Proveedores, empresas del grupo y asociadas",
                                "accounts": (403, 404)
                            },
                            {"parent": "3. Acreedores varios.", "accounts": (410, )},
                            {"parent": "4. Personal (remuneraciones pendientes de pago).", "accounts": (465, 466)},
                            {"parent": "5. Pasivos por impuesto corriente.", "accounts": (4752, )},
                            {
                                "parent": "6. Otras deudas con las Administraciones Públicas.",
                                "accounts": (4750, 4751, 4758, 476, 477)
                            },
                            {
                                "parent": "7. Anticipos de clientes.",
                                "accounts": (438, )
                            }
                        ]
                    },
                    {
                        "parent": "VI. Periodificaciones a corto plazo", "accounts": (485, 568)
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
                    width: 98%;
                    margin-left: auto; 
                    margin-right: 0;
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

        # Añadir las entradas de la tabla
        for main_title in balance_sheet_skeleton:
            body_html += f"""
            <div class="observations">{main_title["parent"]}</div>
                <div style="width:95%;">
            """
            body_html = accounts_html(main_title["children"], main_title["title_format"], body_html)
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
        
        # Combinar el contenido del encabezado y el cuerpo
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
