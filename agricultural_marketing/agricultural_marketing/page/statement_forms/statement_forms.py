import json
import os
import random

import frappe
from frappe import _
from frappe.utils import getdate, flt
from frappe.utils.jinja_globals import is_rtl
from frappe.utils.pdf import get_pdf as _get_pdf
from frappe.query_builder import Order
from pypika import Case


# TODO: Cod need refactoring
@frappe.whitelist()
def get_reports(filters):
    data = frappe._dict()
    file_urls = []
    if isinstance(filters, str):
        filters = json.loads(filters)

    # Get Data
    data = get_data(data, filters)
    if not data:
        return {
            "error": "No data matches the chosen criteria"
        }
    html_format = get_html_format()

    for key, value in data.items():
        # Get summary table data
        party_summary = get_party_summary(filters=filters, party_type=filters.get("party_type"), party=key,
                                          party_data=value)

        header_details = get_header_data(filters.get("party_group"), key)
        context = {
            "header": header_details,
            "summary": party_summary,
            "items": value.get("items"),
            "payments": value.get("payments"),
            "filters": filters,
            "lang": frappe.local.lang,
            "layout_direction": "rtl" if is_rtl() else "ltr"
        }

        html = frappe.render_template(html_format, context)
        content = _get_pdf(html, {"orientation": "Landscape"})
        file_name = "{0}-{1}.pdf".format(key, str(random.randint(1000, 9999)))
        file_doc = frappe.new_doc("File")
        file_doc.update({
            "file_name": file_name,
            "is_private": 0,
            "content": content
        })
        file_doc.save(ignore_permissions=True)
        file_urls.append(file_doc.file_url)

    return {
        "file_urls": file_urls
    }


def get_data(data, filters):
    data = get_items_details(data, filters)
    data = get_payments_details(data, filters)
    return data


def get_html_format():
    template_filename = os.path.join("statement_forms" + '.html')
    folder = os.path.dirname(frappe.get_module("agricultural_marketing" + "." + "agricultural_marketing" +
                                               "." + "page").__file__)
    doctype_path = os.path.join(folder, "statement_forms")
    paths_temp = os.path.join(doctype_path, template_filename)
    html_format = frappe.utils.get_html_format(paths_temp)
    return html_format


def get_items_details(data, filters):
    invform = frappe.qb.DocType("Invoice Form")
    invformitem = frappe.qb.DocType("Invoice Form Item")

    _filters = {"is_customer": 1} if filters.get("party_type") == "Customer" else {}
    _field = invformitem.customer if filters.get("party_type") == "Customer" else invform.supplier

    items_query = frappe.qb.from_(invform).left_join(invformitem).on(
        invformitem.parent == invform.name).where(invform.company == filters.get('company'))

    if filters.get('party'):
        parties = [filters.get('party')]
    elif filters.get('party_group'):
        party_group = "customer_group" if filters.get('party_type') == "Customer" else "supplier_group"
        _filters[party_group] = filters.get('party_group')
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")
    else:
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")

    items_query = items_query.where(_field.isin(parties))

    if filters.get("from_date") and filters.get("to_date") and (filters.get("to_date") < filters.get("from_date")):
        frappe.throw(_("To date must be after from date"))

    if filters.get("from_date"):
        items_query = items_query.where(invform.posting_date.gte(filters.get("from_date")))

    if filters.get("to_date"):
        items_query = items_query.where(invform.posting_date.lte(filters.get("to_date")))

    items_query = items_query.where(invform.docstatus == 1)

    items_query = items_query.select(_field.as_("party"), invform.name.as_("invoice_id"),
                                     invform.posting_date.as_("date"), invformitem.qty, invformitem.price,
                                     invformitem.total, invformitem.item_name)

    if filters.get("party_type") == "Supplier":
        items_query = items_query.select(invformitem.commission)

    result = items_query.orderby(_field, invform.posting_date, order=Order.desc).run(as_dict=True)

    for row in result:
        party = row.get("party")
        row.pop("party")
        if party in data:
            data[party]["items"].append(row)
        else:
            data[party] = {}
            data[party]["items"] = [row]

    # Getting Totals
    for key, value in data.items():
        for i, items in value.items():
            total_commission = 0
            total_taxes = 0
            total_commission_with_taxes = 0
            total_qty = sum([it['qty'] for it in items])
            total_before_tax = sum([it['total'] for it in items])

            if filters.get("party_type") == "Supplier":
                total_commission = sum([it['commission'] for it in items])
                tax_rate = get_tax_rate()
                total_taxes = (total_commission * tax_rate) / 100
                total_commission_with_taxes = total_commission + total_taxes

            items.append({
                "date": _("Total Without Taxes"),
                "qty": total_qty,
                "total": total_before_tax,
                "commission": total_commission
            })

            if total_taxes:
                items.append({
                    "date": _("Taxes"),
                    "commission": total_taxes
                })

            items.append({
                "date": _("Total with Taxes"),
                "qty": total_qty,
                "total": total_before_tax,
                "commission": total_commission_with_taxes
            })

    return data


def get_payments_details(data, filters):
    entry = frappe.qb.DocType("Payment Entry")
    payments_query = frappe.qb.from_(entry).where(entry.company == filters.get('company'))

    _filters = {"is_customer": 1} if filters.get("party_type") == "Customer" else {}

    if filters.get("party"):
        parties = [filters.get("party")]
    elif filters.get("party_group"):
        party_group = "customer_group" if filters.get('party_type') == "Customer" else "supplier_group"
        _filters[party_group] = filters.get('party_group')
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")
    else:
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")

    payments_query = payments_query.where(entry.party.isin(parties))
    if filters.get("from_date") and filters.get("to_date") and (filters.get("to_date") < filters.get("from_date")):
        frappe.throw(_("To date must be after from date"))

    if filters.get("from_date"):
        payments_query = payments_query.where(entry.posting_date.gte(filters.get("from_date")))

    if filters.get("to_date"):
        payments_query = payments_query.where(entry.posting_date.lte(filters.get("to_date")))

    payments_query = payments_query.where(entry.docstatus == 1)

    payments_query = payments_query.select(entry.party_type, entry.party, entry.name.as_("payment_id"),
                                           entry.posting_date.as_("date"), entry.mode_of_payment.as_("mop"),
                                           entry.payment_type, entry.remarks)

    if filters.get("party_type") == "Supplier":
        payments_query = payments_query.select(
            Case().when(entry.payment_type == "Pay", entry.paid_amount).
            when(entry.payment_type == "Receive", (entry.paid_amount * -1)).
            else_(entry.paid_amount).as_("paid_amount")
        )
    elif filters.get("party_type") == "Customer":
        payments_query = payments_query.select(
            Case().when(entry.payment_type == "Receive", entry.paid_amount).
            when(entry.payment_type == "Pay", (entry.paid_amount * -1)).
            else_(entry.paid_amount).as_("paid_amount")
        )

    result = payments_query.run(as_dict=True)

    for row in result:
        party = row.get("party")
        row.pop("party")
        if party in data:
            if data[party].get("payments"):
                data[party]["payments"].append(row)
            else:
                data[party]["payments"] = {}
                data[party]["payments"] = [row]
        else:
            data[party] = {}
            data[party]["payments"] = [row]

    # Getting Total
    if result:
        for key, value in data.items():
            for i, payments in value.items():
                if i == "payments":
                    total_amount = sum([p['paid_amount'] for p in payments]) or 0
                    payments.append({
                        "date": _("Grand Total"),
                        "paid_amount": total_amount
                    })

    return data


def get_tax_rate():
    default_tax_template = frappe.db.get_single_value("Agriculture Settings", "default_tax")

    if not default_tax_template:
        default_tax_template = frappe.db.get_value("Sales Taxes and Charges",
                                                   {"is_default": 1}, "name")

    tax_rate = frappe.db.get_value("Sales Taxes and Charges",
                                   {"parent": default_tax_template}, "rate") or 0
    return tax_rate


def get_header_data(party_group, party):
    return {
        "party": party,
        "party_group": party_group
    }


def get_party_summary(filters, party_type, party, party_data):
    def update_balance(balance, debit, credit):
        """Helper function to calculate and update the balance."""
        return balance + flt(debit) - flt(credit)

    def get_total_sales_and_commissions(data):
        if data.get("items"):
            return data["items"][-1].get("total", 0), data["items"][-1].get("commission", 0)
        return 0, 0

    def get_total_payments(data):
        if data.get("payments"):
            return data.get("payments")[-1].get('paid_amount', 0)
        return 0

    def append_summary(statement, debit, credit):
        nonlocal last_balance
        if switch_columns:
            debit, credit = credit, debit

        last_balance = update_balance(last_balance, debit, credit)
        party_summary.append({
            "statement": statement,
            "debit": debit or str(debit),
            "credit": credit or str(credit),
            "balance": last_balance or str(last_balance)
        })

    switch_columns = True if party_type == "Customer" else False
    party_summary = []
    debit, credit, last_balance = 0, 0, 0
    from_date = filters.get('from_date')
    to_date = filters.get('to_date') or getdate()

    gl_filters = {
        "party_type": filters.get("party_type"),
        "party": party,
        "to_date": to_date
    }

    q = """
                select name, debit, credit, posting_date
                from `tabGL Entry`
                where party_type=%(party_type)s and party=%(party)s 
                and is_cancelled = 0
                and (posting_date <= %(to_date)s or is_opening = 'Yes')
            """
    if from_date:
        gl_filters["from_date"] = from_date
        q += """ and (posting_date >= %(from_date)s or is_opening = 'Yes') """
    gl_entries = frappe.db.sql(q, gl_filters, as_dict=True)

    for gl in gl_entries:
        debit += gl.debit
        credit += gl.credit

    # Calculate totals
    total_sales, total_commission_with_taxes = get_total_sales_and_commissions(party_data)
    total_payments = get_total_payments(party_data)
    last_balance = debit - credit

    # Append Opening
    party_summary.append({
        "statement": _("Opening Balance"),
        "debit": debit or "0",
        "credit": credit or "0",
        "balance": last_balance or "0"
    })

    # Append Summaries
    append_summary(_("Duration Selling"), 0, total_sales)
    append_summary(_("Duration Commission"), total_commission_with_taxes, 0)
    append_summary(_("Duration Payments"), total_payments, 0)

    # Calculate and append closing
    total_debit = total_commission_with_taxes + total_payments + debit
    total_credit = total_sales + credit
    party_summary.append({
        "statement": _("Total"),
        "debit": total_debit,
        "credit": total_credit,
        "balance": (total_debit - total_credit) or "0"
    })

    return party_summary
