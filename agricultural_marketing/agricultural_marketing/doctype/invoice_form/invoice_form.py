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

    settings = frappe.get_single("Agriculture Settings")

    def validate(self):
        self.update_grand_total()
        self.update_commission_and_taxes()

    def on_submit(self):
        self.make_gl_entries()
        if self.settings.get("generate_commission_invoices_automatically"):
            self.generate_commission_invoice()

    def on_cancel(self):
        self.cancel_commission_invoice()
        self.make_gl_entries_on_cancel()

    def on_trash(self):
        # delete gl entries on deletion of transaction
        if frappe.db.get_single_value("Accounts Settings", "delete_linked_ledger_entries"):
            gles = frappe.get_all("GL Entry",
                                  {"voucher_type": self.doctype, "voucher_no": self.name}, pluck="name")
            for gle in gles:
                frappe.delete_doc("GL Entry", gle, for_reload=True)
        # delete commission invoice on deletion of transaction
        self.delete_commission_invoice()

    def update_grand_total(self):
        self.grand_total = 0
        for item in self.items:
            self.grand_total += item.total

    def update_commission_and_taxes(self):
        commission_item = self.settings.get("commission_item")
        if commission_item:
            self.set("commissions", [])
            commission_percentage = get_party_commission_percentage("Customer", self.supplier)
            default_tax = self.settings.get("default_tax", 0)
            price_after_commission = (self.grand_total * commission_percentage) / 100
            commission_total_with_taxes = (
                    price_after_commission + ((price_after_commission * default_tax) / 100)
            )
            self.append("commissions", {
                "item": commission_item,
                "price": self.grand_total,
                "commission": commission_percentage,
                "taxes": default_tax,
                "commission_total": commission_total_with_taxes
            })
            for item in self.items:
                item.commission = (item.total * commission_percentage) / 100

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
        supplier_related_customer = frappe.db.get_value("Supplier", self.supplier, "related_customer")
        gl_entries.append({
            "posting_date": self.posting_date,
            "due_date": self.posting_date,
            "account": get_party_account("Customer", supplier_related_customer, self.company),
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

    def generate_commission_invoice(self):
        if len(self.commissions) == 0:
            return

        # check supplier's related customer
        supplier_related_customer = frappe.db.get_value("Supplier", self.supplier, "related_customer")
        if not supplier_related_customer:
            frappe.throw(_("Supplier is not linked to a customer"))

        # Calculate total commission amount
        total_commission = 0
        for it in self.commissions:
            total_commission += (it.price * it.commission) / 100

        # Generate the commission sales invoice
        pos_profile = frappe.get_doc("POS Profile", self.settings.get("pos_profile"))
        commission_invoice = create_commission_invoice(self.name, supplier_related_customer, pos_profile,
                                                       self.settings.get("commission_item"), total_commission)
        self.db_set("commission_invoice_reference", commission_invoice.name)

    def cancel_commission_invoice(self):
        if self.commission_invoice_reference:
            commission_invoice = frappe.get_doc("Sales Invoice", self.commission_invoice_reference)
            if commission_invoice.docstatus == 0:
                commission_invoice.run_method("on_trash")
                frappe.delete_doc("Sales Invoice", self.commission_invoice_reference, for_reload=True)
                self.db_set("commission_invoice_reference", "")
            if commission_invoice.docstatus == 1:
                commission_invoice.cancel()

    def delete_commission_invoice(self):
        if self.commission_invoice_reference:
            commission_invoice = frappe.get_doc("Sales Invoice", self.commission_invoice_reference)
            if commission_invoice.docstatus == 2:
                commission_invoice.run_method("on_trash")
                frappe.delete_doc("Sales Invoice", self.commission_invoice_reference, for_reload=True)
            else:
                if commission_invoice.docstatus == 0:
                    commission_invoice.run_method("on_trash")
                    frappe.delete_doc("Sales Invoice", self.commission_invoice_reference, for_reload=True)
                if commission_invoice.docstatus == 1:
                    commission_invoice.cancel()


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

    # Get the percentage from the Agriculture Settings single doc
    return frappe.get_single("Agriculture Settings").get("customer_commission_percentage", 0)


def create_commission_invoice(invoice_id, supplier_related_customer, pos_profile, commission_item, total_commission):
    commission_invoice = frappe.new_doc("Sales Invoice")
    commission_invoice.update({
        "customer": supplier_related_customer,
        "is_pos": 1,
        "pos_profile": pos_profile.get("name")
    })
    commission_invoice.append("items", {
        "item_code": commission_item,
        "description": commission_item + "\n" + invoice_id,
        "qty": 1,
        "rate": total_commission
    })
    for mop in pos_profile.get("payments", []):
        if mop.default:
            default_mop = mop.mode_of_payment

    commission_invoice.append("payments", {
        "mode_of_payment": default_mop,
        "amount": total_commission
    })
    commission_invoice.save()
    return commission_invoice
