import frappe
from frappe.utils import nowdate, add_days

@frappe.whitelist()
def get_reconciled_transaction_count():
    # Obtener el número de transacciones reconciliadas hoy
    count = frappe.db.count(
        'Bank Transaction',
        filters={
            'status': 'Reconciled',
            'modified': ['between', [nowdate(), add_days(nowdate(), 1)]]
        }
    )
    
    # Retornar el valor en el formato requerido
    return {
        "value": count,  # Número total de transacciones reconciliadas
        "fieldtype": "Int",  # Tipo de campo en la tarjeta (puede ser Int o Number)
        "route_options": {"from_date": nowdate()},  # Opcional: Rutas dinámicas si se necesita enlazar
        "route": None  # No redirige a un informe en este caso
    }

import frappe
from frappe.utils import get_datetime, now_datetime

@frappe.whitelist()
def get_prom_reconciled_transaction():
    # Definir el inicio del lunes de esta semana (25/11/2024 a las 00:00)
    start_of_week = get_datetime("2024-11-25 00:00:00")
    
    # Obtener la fecha y hora actual
    current_datetime = now_datetime()
    
    # Ejecutar un query para contar transacciones agrupadas por hora
    result = frappe.db.sql("""
        SELECT 
            DATE_FORMAT(modified, '%%Y-%%m-%%d %%H:00:00') AS hour_group,
            COUNT(*) AS transaction_count
        FROM `tabBank Transaction`
        WHERE 
            status = 'Reconciled'
            AND modified >= %(start_of_week)s
        GROUP BY hour_group
    """, {"start_of_week": start_of_week}, as_dict=True)
    
    # Extraer la cantidad de transacciones por cada hora
    hourly_counts = [row["transaction_count"] for row in result]
    
    # Calcular la media de transacciones por hora
    avg_per_hour = sum(hourly_counts) / len(hourly_counts) if hourly_counts else 0
    
    # Formatear la respuesta para la tarjeta
    return {
        "value": round(avg_per_hour, 2),  # Redondear a dos decimales
        "fieldtype": "Float",  # Tipo de campo para la tarjeta
        "route_options": {"from_date": start_of_week.strftime('%Y-%m-%d')},
        "route": None  # No redirige a un informe
    }
