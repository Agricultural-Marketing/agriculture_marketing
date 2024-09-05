import json
import os
import random

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.utils.jinja_globals import is_rtl
from frappe.utils.pdf import get_pdf as _get_pdf
from erpnext.accounts.utils import get_balance_on
from frappe.query_builder import Order


# TODO: الكود محتاج يتروووووق و يتنضف


@frappe.whitelist()
def get_reports(filters):
    data = frappe._dict()
    file_urls = []
    if isinstance(filters, str):
        filters = json.loads(filters)

    # Get Data
    data = get_data(data, filters)
    html_format = get_html_format()

    for key, value in data.items():
        header_details = get_header_data(key)
        context = {"header": header_details, "items": value.get("items"), "payments": value.get("payments"),
                   "filters": filters, "lang": frappe.local.lang, "layout_direction": "rtl" if is_rtl() else "ltr"}

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

    return file_urls


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

    items_query = frappe.qb.from_(invform).left_join(invformitem).on(
        invformitem.parent == invform.name).where(invform.company == filters.get('company'))

    if filters.get("party_type") == "Customer":
        _field = invformitem.customer
        _filters = {"is_customer": 1}
    elif filters.get("party_type") == "Supplier":
        _field = invform.supplier
        _filters = {}

    if filters.get('party'):
        parties = [filters.get('party')]
    else:
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")

    items_query = items_query.where(_field.isin(parties))

    if filters.get("from_date") and filters.get("to_date") and (filters.get("to_date") < filters.get("from_date")):
        frappe.throw(_("To date must be after from date"))

    if filters.get("from_date"):
        items_query = items_query.where(invform.posting_date.gte(filters.get("from_date")))

    if filters.get("to_date"):
        items_query = items_query.where(invform.posting_date.lte(filters.get("to_date")))

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
                total_commission_with_taxes = total_commission - total_taxes

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
    else:
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")

    payments_query = payments_query.where(entry.party.isin(parties))
    if filters.get("from_date") and filters.get("to_date") and (filters.get("to_date") < filters.get("from_date")):
        frappe.throw(_("To date must be after from date"))

    if filters.get("from_date"):
        payments_query = payments_query.where(entry.posting_date.gte(filters.get("from_date")))

    if filters.get("to_date"):
        payments_query = payments_query.where(entry.posting_date.lte(filters.get("to_date")))

    result = payments_query.select(entry.party, entry.name.as_("payment_id"), entry.posting_date.as_("date"),
                                   entry.mode_of_payment.as_("mop"), entry.payment_type, entry.remarks,
                                   entry.paid_amount).run(as_dict=True)

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


def get_header_data(party):
    return {
        "party": party
    }
