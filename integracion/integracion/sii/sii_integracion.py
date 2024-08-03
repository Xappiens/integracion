# sii_integration.py
import frappe
from .method.facturas_emitidas import enviar_facturas_emitidas
from .method.facturas_recibidas import enviar_facturas_recibidas

@frappe.whitelist()
def enviar_facturas_emitidas_wrapper(docnames):
    return enviar_facturas_emitidas(docnames)

@frappe.whitelist()
def enviar_facturas_recibidas_wrapper(docnames):
    return enviar_facturas_recibidas(docnames)
