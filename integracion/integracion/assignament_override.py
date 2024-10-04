import frappe
from frappe.automation.doctype.assignment_rule.assignment_rule import AssignmentRule
from frappe.desk.form import assign_to  # Importar assign_to
from frappe import _

class AssignmentRuleOverride(AssignmentRule):
    def get_user(self, doc):
        """
        Override method to add custom rules including 'Todos'
        """
        if self.rule == "Todos":
            return self.get_all_users()  # Asignar a todos los usuarios
        else:
            return super().get_user(doc)

    def get_all_users(self):
        """
        Get all users for assignment (similar to Round Robin but assigns to all).
        """
        # Obtener todos los usuarios definidos en la tabla 'users'
        return [d.user for d in self.users]  # Retorna una lista de todos los usuarios en la regla

    def do_assignment(self, doc):
        """
        Override the assignment logic to handle assigning to multiple users when rule is 'Todos'
        """
        assign_to.clear(doc.get("doctype"), doc.get("name"), ignore_permissions=True)

        if self.rule == "Todos":
            # Asignar a todos los usuarios
            users = self.get_all_users()
        else:
            # Si no es la regla 'Todos', usar la lógica normal
            users = [self.get_user(doc)]

        if users:
            assign_to.add(
                dict(
                    assign_to=users,
                    doctype=doc.get("doctype"),
                    name=doc.get("name"),
                    description=frappe.render_template(self.description, doc),
                    assignment_rule=self.name,
                    notify=True,
                    date=doc.get(self.due_date_based_on) if self.due_date_based_on else None,
                ),
                ignore_permissions=True,
            )

            # Si es 'Round Robin', actualizar el último usuario asignado.
            # Para 'Todos', no necesitamos setear 'last_user', lo dejamos vacío o None.
            if self.rule == "Round Robin":
                self.db_set("last_user", users[0])
            elif self.rule == "Todos":
                self.db_set("last_user", None)  # Dejar vacío el last_user para la regla 'Todos'

            return True

        return False
