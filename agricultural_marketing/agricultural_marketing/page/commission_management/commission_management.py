import json

from pypika.functions import Sum

import frappe
from agricultural_marketing.agricultural_marketing.doctype.invoice_form.invoice_form import (
    get_supplier_commission_percentage)


@frappe.whitelist()
def execute(filters):
    invoices = []
    if isinstance(filters, str):
        filters = json.loads(filters)

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    party_type = filters.get("party_type")
    party = filters.get("party")

    inv_form = frappe.qb.DocType("Invoice Form")
    inv_frmitem = frappe.qb.DocType("Invoice Form Item")
    if party_type == "Supplier":
        supplier_commission = get_supplier_commission_percentage(party)
        invoices = frappe.qb.from_(inv_form).select(inv_form.name.as_("invoice_id"),
                                                    inv_form.has_supplier_commission_invoice,
                                                    ((inv_form.grand_total * supplier_commission) / 100).as_(
                                                        "total")).where(
            inv_form.supplier == party).where(inv_form.has_supplier_commission_invoice == 0).where(
            inv_form.docstatus == 1).where(inv_form.posting_date.between(from_date, to_date)).run(as_dict=True)

    elif party_type == "Customer":
        invoices = frappe.qb.from_(inv_form).join(inv_frmitem).on(inv_frmitem.parent == inv_form.name).select(
            inv_frmitem.parent.as_("invoice_id"), Sum(inv_frmitem.customer_commission).as_("total")).where(
            inv_frmitem.customer == party).where(inv_form.has_customer_commission_invoices == 0).where(
            inv_form.docstatus == 1).where(inv_form.posting_date.between(from_date, to_date)).groupby(
            inv_frmitem.parent
        ).run(as_dict=True)

    return invoices


@frappe.whitelist()
def generate_commission_invoices(invoices, filters):
    if isinstance(invoices, str):
        invoices = json.loads(invoices)

    if isinstance(filters, str):
        filters = json.loads(filters)

    for invoice in invoices:
        invoice_doc = frappe.get_doc("Invoice Form", invoice["invoice_id"])
        if filters.get("party_type") == "Supplier":
            invoice_doc.generate_supplier_commission_invoice()
        elif filters.get("party_type") == "Customer":
            invoice_doc.generate_customers_commission_invoices()

    return "Invoices Created Successfully"
