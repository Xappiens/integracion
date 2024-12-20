import frappe
from frappe import _

# Para la asignación automática al crear GL Entry
def before_insert(doc, method):
    """
    Asignar número de asiento al crear un GL Entry de forma correlativa
    """
    try:
        # Obtener el número existente si ya hay GL Entries para este voucher
        existing_number = frappe.db.get_value("GL Entry", {
            "voucher_type": doc.voucher_type,
            "voucher_no": doc.voucher_no,
            "company": doc.company
        }, "custom_numero")

        if existing_number:
            doc.custom_numero = existing_number
        else:
            # Si no existe, obtener el último número usado para cualquier asiento de ese año
            last_number = frappe.db.sql("""
                SELECT MAX(custom_numero) 
                FROM `tabGL Entry`
                WHERE YEAR(posting_date) = YEAR(%s)
                AND company = %s
            """, (doc.posting_date, doc.company))[0][0] or 0
            
            # Asignar nuevo número
            nuevo_numero = last_number + 1
            doc.custom_numero = nuevo_numero
            
            # Si es un Journal Entry, actualizar también su número
            if doc.voucher_type == "Journal Entry":
                frappe.db.set_value("Journal Entry", doc.voucher_no, "number", nuevo_numero)

    except Exception as e:
        frappe.log_error(f"Error al asignar número de asiento: {str(e)}")
        raise

# Para renumerar asientos existentes
@frappe.whitelist()
def renumerar_asientos_gl(company, year):
    """
    Renumera los GL Entries por Empresa y Año, ordenando por fecha contable (posting_date)
    y en caso de empate por fecha de creación (creation).
    """
    if not frappe.has_permission("GL Entry", "write"):
        frappe.throw(_("No tiene permisos para renumerar asientos"))
        
    try:
        # Validar entradas
        if not company or not year:
            frappe.throw(_("Debe proporcionar Empresa y Año."))
        
        # Validar año
        try:
            year = int(year)
            if year < 1900 or year > 2100:
                frappe.throw(_("El año debe estar entre 1900 y 2100"))
        except ValueError:
            frappe.throw(_("El año debe ser un número válido"))
            
        # Obtener los vouchers únicos ordenados por fecha
        vouchers = frappe.db.sql("""
            SELECT DISTINCT voucher_type, voucher_no, MIN(posting_date) as posting_date,
                          MIN(creation) as creation
            FROM `tabGL Entry`
            WHERE company = %s
            AND YEAR(posting_date) = %s
            GROUP BY voucher_type, voucher_no
            ORDER BY MIN(posting_date) ASC, MIN(creation) ASC
        """, (company, year), as_dict=1)
        
        if not vouchers:
            frappe.throw(_("No se encontraron asientos para renumerar en el año {0}").format(year))
        
        total_vouchers = len(vouchers)
        
        # Emitir el total de asientos a procesar
        frappe.publish_realtime(
            "renumerar_asientos_progress",
            {"progress": [0, total_vouchers], "message": _("Iniciando renumeración...")}
        )
            
        # Renumerar secuencialmente
        for idx, voucher in enumerate(vouchers, start=1):
            # Actualizar todos los GL Entries del mismo voucher con el mismo número
            frappe.db.sql("""
                UPDATE `tabGL Entry`
                SET custom_numero = %s
                WHERE voucher_type = %s
                AND voucher_no = %s
                AND company = %s
            """, (idx, voucher.voucher_type, voucher.voucher_no, company))
            
            # Si es un Journal Entry, actualizar también su número
            if voucher.voucher_type == "Journal Entry":
                frappe.db.set_value("Journal Entry", voucher.voucher_no, "number", idx)
            
            # Actualizar progreso cada 10 asientos o en el último
            if idx % 10 == 0 or idx == total_vouchers:
                frappe.publish_realtime(
                    "renumerar_asientos_progress",
                    {
                        "progress": [idx, total_vouchers],
                        "message": _("Renumerando asiento {0} de {1} - Fecha: {2}").format(
                            idx, 
                            total_vouchers,
                            frappe.format(voucher.posting_date, {'fieldtype': 'Date'})
                        )
                    }
                )
                
        frappe.db.commit()
        
        # Mensaje final
        frappe.publish_realtime(
            "renumerar_asientos_progress",
            {
                "success": True,
                "message": _("Renumeración completada"),
                "total_renumerados": total_vouchers
            }
        )
        
        return True
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), _("Error al renumerar asientos"))
        frappe.publish_realtime(
            "renumerar_asientos_progress",
            {
                "success": False,
                "message": str(e)
            }
        )
        frappe.throw(_("Error al renumerar: {0}").format(str(e)))

@frappe.whitelist()
def renumerar_asientos(company, year):
    """
    Renumera los Journal Entries por Empresa y Año, ordenando por fecha contable (posting_date)
    y en caso de empate por fecha de creación (creation).
    """
    if not frappe.has_permission("Journal Entry", "write"):
        frappe.throw(_("No tiene permisos para renumerar Journal Entries"))
        
    try:
        # Validar entradas
        if not company or not year:
            frappe.throw(_("Debe proporcionar Empresa y Año."))
        
        # Validar año
        try:
            year = int(year)
            if year < 1900 or year > 2100:
                frappe.throw(_("El año debe estar entre 1900 y 2100"))
        except ValueError:
            frappe.throw(_("El año debe ser un número válido"))
            
        # Obtener los registros filtrados por Empresa y Año
        journal_entries = frappe.get_all(
            "Journal Entry",
            filters={
                "company": company,
                "posting_date": ["between", [f"{year}-01-01", f"{year}-12-31"]],
                "docstatus": 1
            },
            fields=["name", "posting_date", "creation"],
            order_by="posting_date ASC, creation ASC"  # Primero ordenar por posting_date, luego por creation
        )
        
        if not journal_entries:
            frappe.throw(_("No se encontraron Journal Entries para renumerar en el año {0}").format(year))
        
        total_entries = len(journal_entries)
        
        # Emitir el total de asientos a procesar
        frappe.publish_realtime(
            "renumerar_journal_entries_progress",
            {"progress": [0, total_entries], "message": _("Iniciando renumeración...")}
        )
            
        # Renumerar secuencialmente
        for idx, entry in enumerate(journal_entries, start=1):
            frappe.db.set_value("Journal Entry", entry.name, "number", idx)
            
            # Actualizar progreso cada 10 asientos o en el último
            if idx % 10 == 0 or idx == total_entries:
                frappe.publish_realtime(
                    "renumerar_journal_entries_progress",
                    {
                        "progress": [idx, total_entries],
                        "message": _("Renumerando asiento {0} de {1} - Fecha: {2}").format(
                            idx, 
                            total_entries,
                            frappe.format(entry.posting_date, {'fieldtype': 'Date'})
                        )
                    }
                )
                
        frappe.db.commit()
        
        # Mensaje final
        frappe.publish_realtime(
            "renumerar_journal_entries_progress",
            {
                "success": True,
                "message": _("Renumeración completada"),
                "total_renumerados": total_entries
            }
        )
        
        return True
        
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), _("Error al renumerar Journal Entries"))
        frappe.publish_realtime(
            "renumerar_journal_entries_progress",
            {
                "success": False,
                "message": str(e)
            }
        )
        frappe.throw(_("Error al renumerar: {0}").format(str(e)))