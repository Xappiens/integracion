import frappe
import requests
from frappe import _
from education.education.doctype.student.student import Student

class CustomStudent(Student):

    def update_linked_customer(self):
     try:
        customer = frappe.get_doc("Customer", self.customer)
        if self.customer_group:
            customer.customer_group = self.customer_group
        customer.customer_name = self.student_name
        customer.image = self.image
        customer.save()

        frappe.msgprint(_("Customer {0} updated").format(customer.name), alert=True)

        address = self._create_customer_address(customer)
        if address:
             frappe.msgprint(_("Address {0} processed").format(address.name), alert=True)
        else:
             frappe.msgprint(_("No address processed"), alert=True)
     except Exception as e:
        frappe.log_error(f"Error al actualizar cliente y dirección: {str(e)}", "Update Linked Customer Error")
        raise
            

        
        
    def create_customer(self):
        try:
            frappe.log_error("Inicio de creación de cliente")
             # Buscar si existe un cliente
            customer = self._get_existing_customer()
            
            # Intentar vincular a cliente existente
            if customer:
              frappe.log_error(f"Cliente existente encontrado: {customer}")
              self._link_to_existing_customer(customer)

               # Actualizar o crear dirección para clientes existentes
              address = self._create_customer_address(customer)
              frappe.log_error(f"Dirección procesada: {address.name if address else 'Ninguna'}")
              return
            
            # Crear nuevo cliente
            customer = self._create_new_customer()
            
            # Crear dirección si es posible
            address = self._create_customer_address(customer)
            
            # Vincular cliente al estudiante
            self._link_customer_to_student(customer)
            
            # Mostrar mensaje de éxito apropiado
            self._show_success_message(customer, address)
            
        except Exception as e:
            frappe.log_error(f"Error en create_customer: {str(e)}\nTraza completa: {frappe.get_traceback()}")
            raise

    def _get_existing_customer(self):
        """Busca si existe un cliente con el mismo nombre o DNI"""
        return (
            frappe.db.get_value("Customer", {"customer_name": self.student_name}, "name") or 
            frappe.db.get_value("Customer", {"tax_id": self.dni}, "name")
        )

    def _link_to_existing_customer(self, customer_name):
        """Vincula el estudiante a un cliente existente"""
        frappe.db.set_value("Student", self.name, "customer", customer_name)
        frappe.msgprint(
            _("Student linked to existing Customer {0}").format(customer_name),
            alert=True
        )

    def _create_new_customer(self):
        """Crea un nuevo cliente basado en los datos del estudiante"""
        customer_data = {
            "doctype": "Customer",
            "customer_name": self.student_name,
            "customer_group": self.customer_group or frappe.db.get_single_value("Selling Settings", "customer_group"),
            "customer_type": "Individual",
            "custom_tipo_de_identificacion": "DNI",
            "tax_id": self.dni,
            "email_id": self.student_email_id
        }
     

        # Añadir campos opcionales
        optional_fields = {
            'image': 'image',
            'mobile_no': 'student_mobile_number'
        }
        
        for customer_field, student_field in optional_fields.items():
            if value := getattr(self, student_field, None):
                customer_data[customer_field] = value
        
        customer = frappe.get_doc(customer_data)
        customer.insert(ignore_permissions=True)
        frappe.log_error(f"Cliente creado: {customer.name}", "Customer Creation")
        return customer

    def _create_customer_address(self, customer):
        """Crea una dirección para el cliente si hay suficientes datos"""
        frappe.log_error(message=f"Datos del estudiante: {self.student_name}, {self.address_line_1}, {self.city}, {self.country}, {self.student_email_id}", title="Datos del estudiante")
        if not (hasattr(self, 'address_line_1') and self.address_line_1):
            frappe.log_error("No se creó dirección: Falta address_line_1", "Address Creation Skipped")
            return None
        try:
            existing_address_name = frappe.db.sql("""
                SELECT addr.name
                FROM `tabAddress` addr
                JOIN `tabDynamic Link` dl ON dl.parent = addr.name
                WHERE dl.link_doctype = %s AND dl.link_name = %s
                LIMIT 1
            """, ("Customer", customer.name), as_dict=True)
            # Extraer el nombre de la dirección existente si se encuentra
            if existing_address_name:
                existing_address_name = existing_address_name[0].get("name")

  
            address_data = {
                "doctype": "Address",
                "address_title": self.student_name,
                "address_type": "Billing",
                "address_line1": self.address_line_1,
                "city": getattr(self, 'city', ''),
                "country": getattr(self, 'country', ''),
                "email_id": self.student_email_id,
                "is_primary_address": 1,
                "is_shipping_address": 1,
                "links": [{"link_doctype": "Customer", "link_name": customer.name}]
            }

            # Añadir campos opcionales
            optional_fields = {
                'address_line2': 'address_line_2',
                'state': 'state',
                'pincode': 'postcode',
                'phone': 'student_mobile_number'
            }

            for address_field, student_field in optional_fields.items():
                if value := getattr(self, student_field, None):
                    address_data[address_field] = value
                    
            if existing_address_name:
                # Actualizar dirección existente
                address = frappe.get_doc("Address", existing_address_name)
                address.update(address_data)

                # Verificar y agregar enlace si no existe
                if not any(link.get("link_name") == customer.name for link in address.links):
                    address.append("links", {"link_doctype": "Customer", "link_name": customer.name})

                address.save(ignore_permissions=True)
                frappe.log_error(f"Dirección actualizada: {address.name}", "Address Update Success")
            else:
                # Crear una nueva dirección
                address = frappe.get_doc(address_data)
                address.insert(ignore_permissions=True)
                frappe.log_error(f"Dirección creada: {address.name}", "Address Creation Success")
            
            return address
    
        except Exception as e:
            frappe.log_error(f"Error al crear/actualizar dirección: {str(e)}", "Address Error")
            return None    


       

    def _link_customer_to_student(self, customer):
        """Vincula el cliente creado al estudiante"""
        frappe.db.set_value("Student", self.name, "customer", customer.name)

    def _show_success_message(self, customer, address=None):
        """Muestra el mensaje de éxito apropiado"""
        if address:
            frappe.msgprint(
                _("Customer {0} and Address {1} created and linked to Student").format(
                    customer.name, address.name
                ),
                alert=True
            )
        else:
            frappe.msgprint(
                _("Customer {0} created and linked to Student").format(customer.name),
                alert=True
            )

    def set_missing_customer_details(self):
        """Sobreescribimos para usar nuestro método create_customer"""
        self.set_customer_group()
        if self.customer:
            self.update_linked_customer()
        else:
            self.create_customer()

def get_program_enrollment(
    academic_year,
    academic_term=None,
    program=None,
    batch=None,
    student_category=None,
    course=None,
):
    condition1 = " "
    condition2 = " "
    if academic_term:
        condition1 += " and pe.academic_term = %(academic_term)s"
    if program:
        condition1 += " and pe.program = %(program)s"
    if batch:
        condition1 += " and pe.student_batch_name = %(batch)s"
    if student_category:
        condition1 += " and pe.student_category = %(student_category)s"
    if course:
        condition1 += " and pe.name = pec.parent and pec.course = %(course)s"
        condition2 = ", `tabProgram Enrollment Course` pec"

    return frappe.db.sql(
        """
        select
            pe.student, pe.student_name
        from
            `tabProgram Enrollment` pe {condition2}
        where
            pe.academic_year = %(academic_year)s
            and pe.docstatus = 1 {condition1}
        order by
            pe.student_name asc
        """.format(
            condition1=condition1, condition2=condition2
        ),
        (
            {
                "academic_year": academic_year,
                "academic_term": academic_term,
                "program": program,
                "batch": batch,
                "student_category": student_category,
                "course": course,
            }
        ),
        as_dict=1,
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def fetch_students(doctype, txt, searchfield, start, page_len, filters):
    if filters.get("group_based_on") != "Activity":
        enrolled_students = get_program_enrollment(
            filters.get("academic_year"),
            filters.get("academic_term"),
            filters.get("program"),
            filters.get("batch"),
            filters.get("student_category"),
        )
        student_group_student = frappe.db.sql_list(
            """select student from `tabStudent Group Student` where parent=%s""",
            (filters.get("student_group")),
        )

        students = (
            [d.student for d in enrolled_students if d.student not in student_group_student]
            if enrolled_students
            else [""]
        ) or [""]
        return frappe.db.sql(
            """select name, student_name from tabStudent
            where name in ({0}) and (`{1}` LIKE %s or student_name LIKE %s)
            order by idx desc, name
            limit %s, %s""".format(
                ", ".join(["%s"] * len(students)), searchfield
            ),
            tuple(students + ["%%%s%%" % txt, "%%%s%%" % txt, start, page_len]),
        )
    else:
        return frappe.db.sql(
            """select name, student_name from tabStudent
            where `{0}` LIKE %s or student_name LIKE %s
            order by idx desc, name
            limit %s, %s""".format(
                searchfield
            ),
            tuple(["%%%s%%" % txt, "%%%s%%" % txt, start, page_len]),
        )