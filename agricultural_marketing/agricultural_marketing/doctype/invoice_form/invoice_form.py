# Copyright (c) 2024, Muhammad Salama and contributors
# For license information, please see license.txt
import frappe
from frappe import _
# import frappe
from frappe.model.document import Document


class InvoiceForm(Document):
    def on_update(self):
        self.update_grand_total()

    def on_submit(self):
        self.make_gl_entries()

    def update_grand_total(self):
        self.grand_total = 0
        for item in self.items:
            self.grand_total += item.total

    def make_gl_entries(self):
        gl_entries = []
        if not self.company:
            frappe.throw(_("Please Select a Company"))

        company_defaults = frappe.get_cached_doc("Company", self.company)
        # For credit entry
        self.make_supplier_gl_entry(gl_entries, company_defaults)

        # For debits entries
        self.make_customers_gl_entries(gl_entries, company_defaults)

        for entry in gl_entries:
            gle = frappe.new_doc("GL Entry")
            gle.update(entry)
            gle.flags.ignore_permissions = True
            gle.submit()

    def make_supplier_gl_entry(self, gl_entries, company_defaults):
        gl_entries.append({
            "posting_date": self.posting_date,
            "due_date": self.posting_date,
            "account": company_defaults.default_income_account,
            "party_type": "Supplier",
            "party": self.supplier,
            "credit": self.grand_total,
            "account_currency": company_defaults.default_currency,
            "credit_in_account_currency": self.grand_total,
            "voucher_type": self.doctype,
            "voucher_no": self.name,
            "company": self.company,
            "cost_center": company_defaults.cost_center,
            "credit_in_transaction_currency": self.grand_total,
            "transaction_exchange_rate": 1
        })

    def make_customers_gl_entries(self, gl_entries, company_defaults):
        for it in self.items:
            gl_entries.append({
                "posting_date": self.posting_date,
                "due_date": self.posting_date,
                "account": company_defaults.default_receivable_account,
                "party_type": "Customer",
                "party": it.customer,
                "debit": it.total,
                "account_currency": company_defaults.default_currency,
                "debit_in_account_currency": it.total,
                "voucher_type": self.doctype,
                "voucher_no": self.name,
                "company": self.company,
                "cost_center": company_defaults.cost_center,
                "debit_in_transaction_currency": it.total,
                "transaction_exchange_rate": 1
            })
