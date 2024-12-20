import frappe
from frappe import _

@frappe.whitelist()
def generate_invoices(course_name, price, facturacion_type, cliente=None):
    log_steps = []
    try:
        # Obtén la información del curso
        course = frappe.get_doc("Course", course_name)
        if not course:
            log_steps.append("No se encontró el curso.")
            return {"status": "error", "message": _("No se encontró el curso.")}

        log_steps.append(f"Curso encontrado: {course_name}")

        # Verifica la empresa del curso
        if not course.custom_company:
            log_steps.append("El curso no tiene una empresa asociada.")
            return {"status": "error", "message": _("El curso no tiene una empresa asociada.")}

        log_steps.append(f"Empresa asociada al curso: {course.custom_company}")

        # Obtén información relevante del curso para el campo `terms`
        terms_content = f"""
        <b>Información de la Acción Formativa:</b><br>
        <b>Nombre:</b> {course.course_name or ''}<br>
        <b>Expediente:</b> {course.expediente or ''}<br>
        <b>Órgano Proponente:</b> <em>(Vacío)</em><br>
        <b>Número de Horas:</b> {course.hours or ''}<br>
        <b>Fecha de Impartición:</b> {course.start_date or ''}<br>
        <b>Convocatoria:</b> {course.custom_convocatoria or ''}<br>
        <b>Lugar de Impartición:</b> {course.center or ''}<br>
        <b>Familia Formativa:</b> {course.custom_familia_formativa or ''}<br>
        <b>Área Profesional:</b> {course.custom_area_profesional or ''}<br>
        <b>Fecha de Tramitación:</b> {course.custom_fecha_tramitacion or ''}<br>
        """

        # Obtén el plan formativo y la categoría
        plan = frappe.get_doc("Planes Formativos", course.custom_plan)
        categoria_plan = frappe.get_doc("Planes", plan.cat_plan)
        naming_series = categoria_plan.naming_facturas
        curso_prod = frappe.get_doc("Item", "Curso")

        # Busca la cuenta para debitar
        cuentas_debitar = frappe.get_list(
            "Account",
            filters={
                "company": course.custom_company,
                "account_currency": "EUR"  # Asegúrate de que la moneda sea EUR
            },
            fields=["name", "account_currency"],
            limit_page_length=1
        )

        if not cuentas_debitar:
            log_steps.append("No se encontró una cuenta por defecto para debitar con la moneda EUR.")
            return {"status": "error", "message": _("No se encontró una cuenta por defecto para debitar con la moneda EUR.")}

        cuenta_debitar = cuentas_debitar[0]
        log_steps.append(f"Cuenta seleccionada: {cuenta_debitar['name']} (Moneda: {cuenta_debitar['account_currency']})")

        # Facturación "No Gratuito"
        if facturacion_type == "Estudiantes":
            if not course.custom_estudiantes:
                log_steps.append("No hay estudiantes asignados al curso.")
                return {"status": "error", "message": _("No hay estudiantes asignados al curso.")}

            log_steps.append(f"Hay {len(course.custom_estudiantes)} estudiantes asignados al curso.")

            invoices = []
            for student_entry in course.custom_estudiantes:
                student = student_entry.estudiante
                student_doc = frappe.get_doc("Student", student)
                customer = student_doc.customer

                if not customer:
                    log_steps.append(f"El estudiante {student_doc.student_name} no tiene un cliente asociado.")
                    continue

                log_steps.append(f"Estudiante: {student_doc.student_name}, Cliente: {customer}")

                # Crea la factura para el cliente
                invoice = frappe.get_doc({
                    "doctype": "Sales Invoice",
                    "naming_series": naming_series,
                    "customer": customer,
                    "title": customer,
                    "company": course.custom_company,
                    "posting_date": frappe.utils.today(),
                    "posting_time": frappe.utils.nowtime(),
                    "currency": "EUR",
                    "debit_to": cuenta_debitar["name"],
                    "terms": terms_content,
                    "items": [
                        {
                            "item_name": curso_prod,
                            "description": _("Curso: {0}").format(course.course_name),
                            "qty": 1,
                            "rate": price
                        }
                    ],
                    "due_date": frappe.utils.add_days(frappe.utils.today(), 30)
                })
                invoice.flags.ignore_mandatory = True
                invoice.flags.ignore_validate = True
                invoice.flags.ignore_permissions = True
                invoice.insert()
                invoices.append(invoice.name)

            log_steps.append("Facturas generadas con éxito.")
            return {"status": "success", "message": _("Facturas generadas con éxito."), "invoices": invoices}

        elif facturacion_type == "Empresa":
            if not cliente:
                log_steps.append("Debe proporcionar un cliente para la facturación bonificada.")
                return {"status": "error", "message": _("Debe proporcionar un cliente para la facturación bonificada.")}

            log_steps.append(f"Cliente proporcionado: {cliente}")

            # Crea la factura para el cliente
            invoice = frappe.get_doc({
                "doctype": "Sales Invoice",
                "customer": cliente,
                "title": cliente,
                "company": course.custom_company,
                "posting_date": frappe.utils.today(),
                "posting_time": frappe.utils.nowtime(),
                "naming_series": naming_series,
                "currency": "EUR",
                "debit_to": cuenta_debitar["name"],
                "terms": terms_content,
                "items": [
                    {
                        "item_name": curso_prod,
                        "description": _("Curso: {0}").format(course.course_name),
                        "qty": 1,
                        "rate": price
                    }
                ],
                "due_date": frappe.utils.add_days(frappe.utils.today(), 30)
            })
            invoice.flags.ignore_mandatory = True
            invoice.flags.ignore_validate = True
            invoice.flags.ignore_permissions = True
            invoice.insert()

            log_steps.append(f"Factura creada para el cliente {cliente}: {invoice.name}")
            return {"status": "success", "message": _("Factura generada con éxito."), "invoice": invoice.name}

        else:
            log_steps.append("Tipo de facturación no válido.")
            return {"status": "error", "message": _("Tipo de facturación no válido.")}

    except Exception as e:
        frappe.log_error(message=str(e), title="Error al generar facturas")
        log_steps.append(f"Error: {str(e)}")
        return {"status": "error", "message": _("Error al generar facturas: {0}").format(str(e))}

    finally:
        frappe.log_error(message="\n".join(log_steps), title="Log detallado - Generación de facturas")
