from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import ProfitAndLossStatement
from frappe.utils import flt

class CustomProfitAndLossStatement(ProfitAndLossStatement):
    
    def execute(self, filters=None):
        columns, data, message, chart, report_summary, primitive_summary = super().execute(filters)
        
        # Modificar el formato de los datos para incluir secciones como "OPERACIONES CONTINUADAS"
        data = self.get_custom_data(data)
        
        # Personalizar la apariencia y estilos
        data = self.apply_styles(data)
        
        return columns, data, message, chart, report_summary, primitive_summary
    
    def get_custom_data(self, data):
        custom_data = []
        
        # Insertar la sección "OPERACIONES CONTINUADAS"
        custom_data.append({"account_name": "OPERACIONES CONTINUADAS", "indent": 0, "amount": 0})
        
        # Insertar los datos originales debajo de "OPERACIONES CONTINUADAS"
        for row in data:
            if "Income" in row.get("account_name", ""):
                custom_data.append(row)
        
        # Añadir subtotales y totales personalizados
        custom_data.append(self.get_section_total("Importe neto de la cifra de negocios", custom_data))
        
        return custom_data

    def get_section_total(self, section_name, section_data):
        total = sum([flt(row.get("amount", 0)) for row in section_data])
        return {
            "account_name": section_name,
            "indent": 1,
            "amount": total,
            "is_total": True,
        }

    def apply_styles(self, data):
        # Aplicar estilos como cambiar el color de los valores negativos
        for row in data:
            if row.get("amount") < 0:
                row["account_name"] = f"<span style='color:red;'>{row['account_name']}</span>"
                row["amount"] = f"<span style='color:red;'>{row['amount']}</span>"
            if row.get("is_total"):
                row["account_name"] = f"<b>{row['account_name']}</b>"
                row["amount"] = f"<b>{row['amount']}</b>"
        
        return data

