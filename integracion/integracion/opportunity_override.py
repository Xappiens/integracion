import frappe
from frappe.utils import flt, get_fullname
from erpnext.crm.doctype.opportunity.opportunity import Opportunity

class CustomOpportunity(Opportunity):
    
    def onload(self):
        ref_doc = frappe.get_doc(self.opportunity_from, self.party_name)
        frappe.contacts.address_and_contact.load_address_and_contact(ref_doc)
        self.set("__onload", ref_doc.get("__onload"))
    
    def after_insert(self):
        super().after_insert()  # Llamar a la lógica de la clase base para los casos estándar

        if self.opportunity_from in ["Supplier", "Sales Person"]:
            frappe.get_doc(self.opportunity_from, self.party_name).set_status(update=True)

            frappe.email.inbox.link_communication_to_document(
                self.opportunity_from, self.party_name, self)
    
    def validate(self):
        super().validate()  # Llamar a la validación de la clase base
        self.validate_cust_name()

        if not self.title:
            self.title = self.customer_name
        
        self.calculate_totals()
        self.update_entity()

    def validate_cust_name(self):
        if self.party_name:
            if self.opportunity_from == "Customer":
                self.customer_name = frappe.db.get_value("Customer", self.party_name, "customer_name")
            elif self.opportunity_from == "Lead":
                customer_name = frappe.db.get_value("Prospect Lead", {"lead": self.party_name}, "parent")
                if not customer_name:
                    lead_name, company_name = frappe.db.get_value(
                        "Lead", self.party_name, ["lead_name", "company_name"]
                    )
                    customer_name = company_name or lead_name
                self.customer_name = customer_name
            elif self.opportunity_from == "Prospect":
                self.customer_name = self.party_name
            elif self.opportunity_from == "Supplier":
                self.customer_name = frappe.db.get_value("Supplier", self.party_name, "supplier_name")
            elif self.opportunity_from == "Sales Person":
                self.customer_name = frappe.db.get_value("Sales Person", self.party_name, "employee_name")

    def map_fields(self):
        super().map_fields()  # Llamar al método de la clase base para los campos estándar

        if self.opportunity_from in ["Supplier", "Sales Person"]:
            for field in self.meta.get_valid_columns():
                if not self.get(field) and frappe.db.field_exists(self.opportunity_from, field):
                    try:
                        value = frappe.db.get_value(self.opportunity_from, self.party_name, field)
                        self.set(field, value)
                    except Exception:
                        continue

    def update_entity(self):
        if self.opportunity_from in ["Supplier", "Sales Person"]:
            # You could update specific fields or log an action for the Supplier or Sales Person
            # For example, logging an interaction or updating some details
            entity_doc = frappe.get_doc(self.opportunity_from, self.party_name)
            entity_doc.db_set('last_interaction_date', frappe.utils.nowdate())
            entity_doc.save(ignore_permissions=True)

    def make_new_lead_if_required(self):
        if not self.get("party_name") and self.contact_email:
            dynamic_link, contact = frappe.query_builder.DocType("Dynamic Link"), frappe.query_builder.DocType("Contact")
            customer = (
                frappe.qb.from_(dynamic_link)
                .join(contact)
                .on(
                    (contact.name == dynamic_link.parent)
                    & (dynamic_link.link_doctype == "Customer")
                    & (contact.email_id == self.contact_email)
                )
                .select(dynamic_link.link_name)
                .distinct()
                .run(as_dict=True)
            )

            if customer and customer[0].link_name:
                self.party_name = customer[0].link_name
                self.opportunity_from = "Customer"
                return

            lead_name = frappe.db.get_value("Lead", {"email_id": self.contact_email})
            if not lead_name:
                sender_name = get_fullname(self.contact_email)
                if sender_name == self.contact_email:
                    sender_name = None

                if not sender_name and ("@" in self.contact_email):
                    email_name = self.contact_email.split("@")[0]
                    email_split = email_name.split(".")
                    sender_name = ""
                    for s in email_split:
                        sender_name += s.capitalize() + " "

                lead = frappe.get_doc(
                    {"doctype": "Lead", "email_id": self.contact_email, "lead_name": sender_name or "Unknown"}
                )

                lead.flags.ignore_email_validation = True
                lead.insert(ignore_permissions=True)
                lead_name = lead.name

            self.opportunity_from = "Lead"
            self.party_name = lead_name
