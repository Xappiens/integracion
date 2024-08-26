from hrms.hr.doctype.job_offer.job_offer import JobOffer
import frappe

class CustomJobOffer(JobOffer):

    def on_change(self):
        # Aquí actualizas el estado del solicitante de empleo sin necesidad de usar before_cancel
        self.custom_update_job_applicant(self.status, self.job_applicant)

    def custom_update_job_applicant(self, status, job_applicant):
        # Verificar si el solicitante de empleo existe
        if not job_applicant or not frappe.db.exists("Job Applicant", job_applicant):
            return
        
        # Continuar con la actualización del estado si existe
        if status in ("Accepted", "Rejected", "Cancelled"):
            frappe.set_value("Job Applicant", job_applicant, "status", status)