import json
import os
import random
import frappe
from frappe import _
from frappe.utils import getdate, flt
from frappe.utils.jinja_globals import is_rtl
from frappe.utils.pdf import get_pdf as _get_pdf
from frappe.query_builder.functions import Sum
from pypika import Case


@frappe.whitelist()
def get_reports(filters):
    data = frappe._dict()
    file_urls = []
    letter_head = None
    if isinstance(filters, str):
        filters = json.loads(filters)

    default_letter_head = frappe.get_value("Company", filters.get("company"), "default_letter_head")
    if default_letter_head:
        letter_head = frappe.get_doc("Letter Head", default_letter_head)

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
            "letter_head": letter_head,
            "header": header_details,
            "summary": party_summary,
            "items": value.get("items"),
            "payments": value.get("payments"),
            "filters": filters,
            "lang": frappe.local.lang,
            "layout_direction": "rtl" if is_rtl() else "ltr"
        }

        html = frappe.render_template(html_format, context)
        content = _get_pdf(html, {"orientation": "Portrait"})
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


def get_items_details(data, filters):
    invform = frappe.qb.DocType("Invoice Form")
    invformitem = frappe.qb.DocType("Invoice Form Item")
    items_query = frappe.qb.from_(invform).left_join(invformitem).on(
        invformitem.parent == invform.name).where(invform.company == filters.get('company'))

    # Determine and apply party filters based on party type
    _filters = {"is_customer": 1} if filters.get("party_type") == "Customer" else {}
    _field = invformitem.customer if filters.get("party_type") == "Customer" else invform.supplier
    parties = get_parties(filters, _filters)
    items_query = items_query.where(_field.isin(parties))

    # validate and apply dates filters
    items_query = validate_and_apply_date_filters(filters, items_query, invform)

    # Filter for submitted (docstatus 1) invoice forms
    if filters.get("consider_draft"):
        items_query = items_query.where(invform.docstatus.isin([0, 1]))
    else:
        items_query = items_query.where(invform.docstatus == 1)

    # Select relative fields based on party type
    items_query = select_fields_for_invoices(filters, items_query, _field, invform, invformitem)

    result = items_query.orderby(invform.posting_date).orderby(invform.name).orderby(
        invformitem.item_name).run(as_dict=True)

    if result:
        # Construct result, appending to final data nad appending totals
        process_result_and_totals_for_invoices(result, data, filters)

    return data


def get_payments_details(data, filters):
    entry = frappe.qb.DocType("Payment Entry")
    payments_query = frappe.qb.from_(entry).where(entry.company == filters.get('company'))

    # Determine and apply party filters based on party type
    _filters = {"is_customer": 1} if filters.get("party_type") == "Customer" else {}
    parties = get_parties(filters, _filters)
    payments_query = payments_query.where(entry.party.isin(parties))

    # Validate and apply dates filters
    payments_query = validate_and_apply_date_filters(filters, payments_query, entry)

    # Filter for submitted (docstatus 1) payment entries
    if filters.get("consider_draft"):
        payments_query = payments_query.where(entry.docstatus.isin([0, 1]))
    else:
        payments_query = payments_query.where(entry.docstatus == 1)

    # Select relative fields base on party type
    payments_query = select_fields_for_payment(filters, payments_query, entry)

    result = payments_query.run(as_dict=True)

    if result:
        # Construct result, appending to final data nad appending totals
        process_result_and_totals_for_payments(result, data)

    return data


def get_party_summary(filters, party_type, party, party_data):
    def update_balance(balance, debit, credit):
        """Helper function to calculate and update the balance."""
        return balance + flt(debit) - flt(credit)

    def get_total_sales(data):
        if data.get("items"):
            return sum(it.get("total", 0) for it in data["items"])
        return 0

    def get_total_payments(data):
        if data.get("payments"):
            return sum(it.get("paid_amount", 0) for it in data["payments"])
        return 0

    def append_summary(reference_id, posting_date, statement, debit, credit):
        nonlocal last_balance, balance_from, balance_to
        if switch_columns:
            debit, credit = credit, debit

        last_balance = update_balance(last_balance, debit, credit)
        if last_balance > 0:
            balance_from = last_balance
        else:
            balance_to = last_balance

        party_summary.append({
            "reference": reference_id,
            "date": posting_date,
            "statement": statement,
            "debit": flt(debit, 2) or str(debit),
            "credit": flt(credit, 2) or str(credit),
            "balance_from": abs(flt(balance_from, 2)) or str(balance_from),
            "balance_to": abs(flt(balance_to, 2)) or str(balance_to),
        })

    switch_columns = True if party_type == "Customer" else False
    party_summary = []
    debit, credit, last_balance, balance_from, balance_to = 0, 0, 0, 0, 0
    from_date = filters.get('from_date')

    gl_filters = {
        "party_type": filters.get("party_type"),
        "party": party,
        "from_date": from_date
    }

    q = """ 
            SELECT 
                name, debit, credit, posting_date
            FROM 
                `tabGL Entry`
            WHERE 
                party_type=%(party_type)s 
            AND 
                party=%(party)s 
            AND 
                is_cancelled = 0
            AND 
            (posting_date < %(from_date)s OR is_opening = 'Yes')
        """

    gl_entries = frappe.db.sql(q, gl_filters, as_dict=True)

    for gl in gl_entries:
        debit += gl.debit
        credit += gl.credit

    # GET totals for customers (Opening Balance)
    if filters.get("party_type") == "Customer":
        debit = get_opening_from_sales_invoice_for_customer(filters, party, debit)

    # GET total items and payments before from date
    if filters.get("consider_draft"):
        total_items = get_draft_total_items(filters, party) or 0
        total_payments = get_draft_total_payments(filters, party) or 0
        if filters.get("party_type") == "Supplier":
            debit += total_payments
            credit += total_items
        else:
            debit += total_items
            credit += total_payments

    last_balance = debit - credit
    # Append Opening
    if abs(debit) > abs(credit):
        balance_from = last_balance
        balance_to = 0
    else:
        balance_from = 0
        balance_to = last_balance

    if abs(debit) > abs(credit):
        debit = abs(last_balance)
        credit = 0
    else:
        credit = abs(last_balance)
        debit = 0

    party_summary.append({
        "debit": flt(debit, 2) or "0",
        "credit": flt(credit, 2) or "0",
        "balance_from": abs(flt(balance_from, 2)) or "0",
        "balance_to": abs(flt(balance_to, 2)) or "0",
        "statement": _("Opening Balance"),
    })

    for row in party_data.get("items", []):
        append_summary(row.get("invoice_id"), row.get("date"),
                       f"{row.get('qty')} * {row.get('price')} {row.get('item_name')}", 0, row.get("total"))

    for row in party_data.get("payments", []):
        append_summary(row.get("payment_id"), row.get("date"), row.get("remarks"), row.get("paid_amount"), 0)

    # Calculate totals
    total_sales = get_total_sales(party_data)
    total_payments = get_total_payments(party_data)

    # Calculate and append closing
    if filters.get("party_type") == "Supplier":
        total_commission = sum(it.get("commission", 0) for it in party_data.get("items", []))
        total_taxes = (total_commission * get_tax_rate()) / 100 or 0
        append_summary("", "", _("Commissions"), total_commission, 0)
        append_summary("", "", _("Taxes"), total_taxes, 0)
        total_debit = total_commission + total_payments + total_taxes
        total_credit = total_sales
    else:
        total_debit = total_payments
        total_credit = total_sales

    if switch_columns:
        total_debit, total_credit = total_credit, total_debit

    total_debit += debit
    total_credit += credit

    party_summary.append({
        "statement": _("Total"),
        "debit": flt(total_debit, 2) or "0",
        "credit": flt(total_credit, 2) or "0",
        "balance_from": abs(flt(balance_from, 2)) or "0",
        "balance_to": abs(flt(balance_to, 2)) or "0",
    })

    return party_summary


def get_html_format():
    template_filename = os.path.join("detailed_report" + '.html')
    folder = os.path.dirname(frappe.get_module("agricultural_marketing" + "." + "agricultural_marketing" +
                                               "." + "page").__file__)
    doctype_path = os.path.join(folder, "detailed_report")
    paths_temp = os.path.join(doctype_path, template_filename)
    html_format = frappe.utils.get_html_format(paths_temp)
    return html_format


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


def get_parties(filters, _filters):
    if filters.get("party"):
        parties = [filters.get("party")]
    elif filters.get("party_group"):
        party_group = "customer_group" if filters.get('party_type') == "Customer" else "supplier_group"
        _filters[party_group] = filters.get('party_group')
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")
    else:
        parties = frappe.db.get_all(filters.get("party_type"), _filters, pluck="name")

    return parties


def validate_and_apply_date_filters(filters, query, doctype):
    if filters.get("from_date") and filters.get("to_date") and (filters.get("to_date") < filters.get("from_date")):
        frappe.throw(_("To date must be after from date"))

    if filters.get("from_date"):
        query = query.where(doctype.posting_date.gte(filters.get("from_date")))

    if filters.get("to_date"):
        query = query.where(doctype.posting_date.lte(filters.get("to_date")))

    return query


def select_fields_for_invoices(filters, items_query, _field, invform, invformitem):
    if filters.get("neglect_items"):
        items_query = items_query.select(_field.as_("party"), invform.name.as_("invoice_id"),
                                         invform.posting_date.as_("date"),
                                         invformitem.total)
    else:
        items_query = items_query.select(_field.as_("party"), invform.name.as_("invoice_id"),
                                         invform.posting_date.as_("date"), invformitem.qty, invformitem.price,
                                         invformitem.total, invformitem.item_name)

    if filters.get("party_type") == "Supplier":
        items_query = items_query.select(invformitem.commission)
    else:
        items_query = items_query.select(invformitem.customer_commission.as_("commission"))

    return items_query


def process_result_and_totals_for_invoices(result, data, filters):
    def calculate_totals(items):
        """Calculate the total quantities, before tax, commission, and taxes."""
        total_qty = sum([it.get('qty') for it in items if it.get('qty')])
        total_before_tax = sum([it.get('total') for it in items if it.get('total')])
        total_commission = sum([it.get('commission') for it in items])
        total_taxes = (total_commission * get_tax_rate()) / 100 if total_commission else 0
        total_commission_with_taxes = total_commission + total_taxes
        return total_qty, total_before_tax, total_commission, total_taxes, total_commission_with_taxes

    invoices = set()
    for row in result:
        party = row.pop("party")  # Extract and remove party from the row
        invoice_id = row.get("invoice_id")
        if invoice_id in invoices and filters.get("neglect_items"):
            for d in data[party]["items"]:
                if d["invoice_id"] == invoice_id:
                    d["total"] += row["total"]
                    if filters.get("party_type") == "Supplier":
                        d["commission"] += row["commission"]
                    break
        else:
            data.setdefault(party, {}).setdefault("items", []).append(row)
            invoices.add(row["invoice_id"])


def select_fields_for_payment(filters, payments_query, entry):
    payments_query = payments_query.select(entry.party_type, entry.party, entry.name.as_("payment_id"),
                                           entry.posting_date.as_("date"), entry.mode_of_payment.as_("mop"),
                                           entry.payment_type, entry.remarks)

    # Conditionally select paid amount based on party type and payment type
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

    return payments_query


def process_result_and_totals_for_payments(result, data):
    def append_to_date(party, row):
        """Append payment row to the desired party in data"""
        if party not in data:
            data[party] = {"payments": []}
        data.setdefault(party, {}).setdefault("payments", []).append(row)

    def calculate_grand_total(payments):
        """Calculate the total paid amount"""
        total_amount = sum(p.get('paid_amount', 0) for p in payments)
        payments.append({
            "date": _("Total"),
            "paid_amount": total_amount
        })

    for row in result:
        party = row.pop("party", None)
        if party:
            append_to_date(party, row)


def get_draft_total_items(filters, party):
    invform = frappe.qb.DocType("Invoice Form")
    invformitem = frappe.qb.DocType("Invoice Form Item")
    items_query = frappe.qb.from_(invform).left_join(invformitem).on(
        invformitem.parent == invform.name).where(invform.company == filters.get('company'))

    # Determine and apply party filters based on party type
    _field = invformitem.customer if filters.get("party_type") == "Customer" else invform.supplier
    items_query = items_query.where(_field == party)

    items_query = items_query.where(invform.docstatus == 0).where(invform.posting_date.lt(filters.get("from_date")))

    # Select relative fields based on party type
    result = items_query.select(Sum(invformitem.total).as_("total")).run(as_dict=True)

    total_items = sum([re["total"] for re in result if re["total"]]) or 0

    return total_items


def get_draft_total_payments(filters, party):
    entry = frappe.qb.DocType("Payment Entry")
    payments_query = frappe.qb.from_(entry).where(
        entry.company == filters.get('company')).where(
        entry.party == party).where(
        entry.posting_date.lt(filters.get("from_date"))).where(
        entry.docstatus == 0
    )

    payments_query = payments_query.select(entry.payment_type)

    # Conditionally select paid amount based on party type and payment type
    if filters.get("party_type") == "Supplier":
        payments_query = payments_query.select(
            Case().when(entry.payment_type == "Pay", Sum(entry.paid_amount)).
            when(entry.payment_type == "Receive", (Sum(entry.paid_amount * -1))).
            else_(Sum(entry.paid_amount)).as_("paid_amount")
        )
    elif filters.get("party_type") == "Customer":
        payments_query = payments_query.select(
            Case().when(entry.payment_type == "Receive", Sum(entry.paid_amount)).
            when(entry.payment_type == "Pay", (Sum(entry.paid_amount * -1))).
            else_(Sum(entry.paid_amount)).as_("paid_amount")
        )

    result = payments_query.run(as_dict=True)

    total_paid_amount = sum([re["paid_amount"] for re in result if re["paid_amount"]]) or 0

    return total_paid_amount


def get_opening_from_sales_invoice_for_customer(filters, party, debit):
    # Get total commission from submitted invoice form which have no commission invoices before the selected date
    invform = frappe.qb.DocType("Invoice Form")
    invformitem = frappe.qb.DocType("Invoice Form Item")
    result = frappe.qb.from_(invform).left_join(invformitem).on(invformitem.parent == invform.name).where(
        invform.company == filters.get('company')).where(invformitem.customer == party).where(
        invform.docstatus == 1).where(invform.posting_date.lt(filters.get("from_date"))).where(
        invformitem.has_commission_invoice == 0).select(Sum(invformitem.customer_commission).as_("total")).run(
        as_dict=True)

    total_commission = sum([re["total"] for re in result if re["total"]]) or 0
    total_taxes = (total_commission * get_tax_rate()) / 100

    debit += total_commission + total_taxes

    # Get totals from sales invoice before the selected date
    sinv = frappe.qb.DocType("Sales Invoice")
    sinv_result = frappe.qb.from_(sinv).where(sinv.company == filters.get("company")).where(
        sinv.customer == party).where(sinv.is_commission_invoice == 1).where(sinv.docstatus == 0).where(
        sinv.posting_date.lt(filters.get("from_date"))).select(sinv.grand_total.as_("total")).run(as_dict=True)
    debit += sum([re["total"] for re in sinv_result if re["total"]]) or 0

    return debit
