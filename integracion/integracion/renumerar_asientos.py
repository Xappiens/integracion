import frappe
from frappe import _

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