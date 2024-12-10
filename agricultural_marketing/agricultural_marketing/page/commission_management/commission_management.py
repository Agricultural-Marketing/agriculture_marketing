import json

from pypika.functions import Sum

import frappe
from frappe import _
from agricultural_marketing.agricultural_marketing.doctype.invoice_form.invoice_form import (
    get_supplier_commission_percentage)
from frappe.utils import getdate


@frappe.whitelist()
def get_invoices(filters):
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

        prev_invoices_query = frappe.qb.from_(inv_form).select(
            inv_form.name.as_("invoice_id"), inv_form.supplier, inv_form.has_supplier_commission_invoice,
            inv_form.grand_total).where(inv_form.has_supplier_commission_invoice == 0).where(
            inv_form.docstatus == 1).where(inv_form.posting_date.lt(from_date))
        if party:
            prev_invoices_query = prev_invoices_query.where(inv_form.supplier == party)

        prev_invoices = prev_invoices_query.run(as_dict=True)

        if prev_invoices:
            return {
                "invoices": [],
                "success": False,
                "msg": _("There are commission invoices that were not created before this duration.")
            }

        invoices_query = frappe.qb.from_(inv_form).select(
            inv_form.name.as_("invoice_id"), inv_form.supplier, inv_form.has_supplier_commission_invoice,
            inv_form.grand_total).where(inv_form.has_supplier_commission_invoice == 0).where(
            inv_form.docstatus == 1).where(inv_form.posting_date.between(from_date, to_date))

        if party:
            invoices_query = invoices_query.where(inv_form.supplier == party)

        invoices = invoices_query.run(as_dict=True)
        if invoices:
            for invoice in invoices:
                supplier_commission = get_supplier_commission_percentage(invoice["supplier"])
                invoice["total"] = (supplier_commission * invoice["grand_total"]) / 100

    elif party_type == "Customer":
        prev_invoices_query = frappe.qb.from_(inv_form).join(inv_frmitem).on(
            inv_frmitem.parent == inv_form.name).select(
            inv_frmitem.parent.as_("invoice_id"), Sum(inv_frmitem.customer_commission).as_("total")).where(
            inv_form.has_customer_commission_invoices == 0).where(
            inv_form.docstatus == 1).where(inv_form.posting_date.lt(from_date)).groupby(
            inv_frmitem.parent)

        if party:
            prev_invoices_query = prev_invoices_query.where(inv_frmitem.customer == party)

        prev_invoices = prev_invoices_query.run(as_dict=True)

        if prev_invoices:
            return {
                "invoices": [],
                "success": False,
                "msg": _("There are commission invoices that were not created before this duration.")
            }

        invoices_query = frappe.qb.from_(inv_form).join(inv_frmitem).on(inv_frmitem.parent == inv_form.name).select(
            inv_frmitem.parent.as_("invoice_id"), inv_frmitem.customer.as_("party"),
            Sum(inv_frmitem.customer_commission).as_("total")).where(
            inv_form.has_customer_commission_invoices == 0).where(
            inv_form.docstatus == 1).where(inv_form.posting_date.between(from_date, to_date)).groupby(
            inv_frmitem.parent)
        if party:
            invoices_query = invoices_query.where(inv_frmitem.customer == party)

        invoices = invoices_query.run(as_dict=True)

    return {
        "invoices": invoices,
        "success": True,
        "msg": _("Invoices retrieved successfully.")
    }


@frappe.whitelist()
def generate_commission_invoices(invoices, filters):
    # Parse input if provided as strings
    if isinstance(invoices, str):
        invoices = json.loads(invoices)
    if isinstance(filters, str):
        filters = json.loads(filters)

    posting_date = filters.get("posting_date", getdate())
    party_type = filters.get("party_type")
    failed_invoices = []

    for invoice in invoices:
        try:
            invoice_doc = frappe.get_doc("Invoice Form", invoice["invoice_id"])
            if party_type == "Supplier":
                invoice_doc.generate_supplier_commission_invoice(posting_date)
            elif party_type == "Customer":
                invoice_doc.generate_customers_commission_invoices(posting_date)
        except Exception:
            failed_invoices.append(invoice["invoice_id"])

    return {
        "failed_invoices": failed_invoices,
        "msg": (
            "Invoices created but with some missing." if failed_invoices
            else "Invoices created successfully."
        )
    }
