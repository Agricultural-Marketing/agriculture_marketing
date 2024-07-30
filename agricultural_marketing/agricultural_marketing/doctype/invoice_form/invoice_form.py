# Copyright (c) 2024, Muhammad Salama and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.model.document import Document
from erpnext.accounts.general_ledger import validate_accounting_period, make_entry
from erpnext.accounts.party import get_party_account
from frappe.utils import now
import copy


class InvoiceForm(Document):
    def validate(self):
        self.update_grand_total()
        self.update_commission_and_taxes()
        self.calculate_item_line_commission()

    def on_submit(self):
        self.make_gl_entries()

    def on_cancel(self):
        self.make_gl_entries_on_cancel()

    def on_trash(self):
        # delete gl entries on deletion of transaction
        if frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"):
            frappe.db.sql(
                "delete from `tabGL Entry` where voucher_type=%s and voucher_no=%s", (self.doctype, self.name)
            )

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
            "account": get_party_account("Customer", self.supplier, self.company),
            "party_type": "Customer",
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

    def make_gl_entries_on_cancel(self):
        gl_entry = frappe.qb.DocType("GL Entry")
        gl_entries = (
            frappe.qb.from_(gl_entry)
            .select("*")
            .where(gl_entry.voucher_type == self.doctype)
            .where(gl_entry.voucher_no == self.name)
            .where(gl_entry.is_cancelled == 0)
            .for_update()
        ).run(as_dict=1)
        if gl_entries:
            self.flags.ignore_links = True
            validate_accounting_period(gl_entries)
            set_as_cancel(self.doctype, self.name)

            for entry in gl_entries:
                new_gle = copy.deepcopy(entry)
                new_gle["name"] = None
                debit = new_gle.get("debit", 0)
                credit = new_gle.get("credit", 0)

                debit_in_account_currency = new_gle.get("debit_in_account_currency", 0)
                credit_in_account_currency = new_gle.get("credit_in_account_currency", 0)

                new_gle["debit"] = credit
                new_gle["credit"] = debit
                new_gle["debit_in_account_currency"] = credit_in_account_currency
                new_gle["credit_in_account_currency"] = debit_in_account_currency

                new_gle["remarks"] = "On cancellation of " + new_gle["voucher_no"]
                new_gle["is_cancelled"] = 1

                if new_gle["debit"] or new_gle["credit"]:
                    make_entry(new_gle, False, "Yes")

    def update_commission_and_taxes(self):
        commission_percentage = get_party_commission_percentage("Customer", self.supplier)
        default_tax = frappe.get_single("Commission Settings").get("default_tax", 0)
        if self.commissions:
            for it in self.commissions:
                it.price = self.grand_total
                it.commission = commission_percentage
                it.taxes = it.taxes if it.taxes else default_tax
                price_after_commission = (self.grand_total * it.commission) / 100
                commission_total_with_taxes = (
                        price_after_commission + ((price_after_commission * it.taxes) / 100)
                )
                it.commission_total = commission_total_with_taxes

    def calculate_item_line_commission(self):
        commission_percentage = get_party_commission_percentage("Customer", self.supplier)
        if self.commissions:
            for item in self.items:
                item.commission = (item.total * commission_percentage) / 100



def set_as_cancel(voucher_type, voucher_no):
    """
    Set is_cancelled=1 in all original gl entries for the voucher
    """
    frappe.db.sql(
        """UPDATE `tabGL Entry` SET is_cancelled = 1,
        modified=%s, modified_by=%s
        where voucher_type=%s and voucher_no=%s and is_cancelled = 0""",
        (now(), frappe.session.user, voucher_type, voucher_no),
    )


def get_party_commission_percentage(party_type, party):
    """
    Returns the commission percentage for the given `party`.
    Will first search in party (Customer / Supplier) record, if not found,
    will search in group (Customer Group / Supplier Group),
    finally will return default."""

    # Get the percentage from the party doc
    commission_percentage = frappe.db.get_value(party_type, party, "commission_percentage")
    if commission_percentage:
        return commission_percentage

    # Get the percentage from the party group doc
    party_group_doctype = "Customer Group" if party_type == "Customer" else "Supplier Group"
    group_field_name = "customer_group" if party_type == "Customer" else "supplier_group"
    party_group = frappe.db.get_value(party_type, party,group_field_name)
    commission_percentage = frappe.db.get_value(party_group_doctype, party_group, "commission_percentage")
    if commission_percentage:
        return commission_percentage

    # Get the percentage from the commission settings single doc
    return frappe.get_single("Commission Settings").get("customer_commission_percentage", 0)
