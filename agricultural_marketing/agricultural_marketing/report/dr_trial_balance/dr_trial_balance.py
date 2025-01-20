# Copyright (c) 2025, Muhammad Salama and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from pypika import Case


def execute(filters=None):
    columns, data = [], []
    columns = get_columns()
    trial_balance_settings = frappe.get_single("Trial Balance Settings")
    data = get_data(filters, trial_balance_settings)
    return columns, data


def get_data(filters, trial_balance_settings):
    result = []
    gl_filters = {
        "company": filters.get("company"),
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date")
    }

    get_child_data_from_gl_entries(gl_filters, trial_balance_settings, "cash_section", result)
    get_customers_section_data(filters, trial_balance_settings, "customers_section", result)
    get_suppliers_section_data(filters, trial_balance_settings, "suppliers_section", result)
    get_child_data_from_gl_entries(gl_filters, trial_balance_settings, "share_capital_section", result)
    get_taxes_section_data(filters, trial_balance_settings, "taxes_section", result)
    get_child_data_from_gl_entries(gl_filters, trial_balance_settings, "income_section", result)
    get_child_data_from_gl_entries(gl_filters, trial_balance_settings, "expense_section", result)

    return result


def get_child_data_from_gl_entries(gl_filters, trial_balance_settings, child, result):
    def get_opening_balances_from_gl():
        opening_debit, opening_credit = 0, 0
        q = """ SELECT 
                    name, debit, credit, posting_date 
                FROM 
                    `tabGL Entry` 
                WHERE 
                    account=%(account)s 
                AND 
                    is_cancelled = 0 
                AND 
                    (posting_date < %(from_date)s OR is_opening = 'Yes') 
        """

        gl_entries = frappe.db.sql(q, gl_filters, as_dict=True)

        for gl in gl_entries:
            opening_debit += gl.debit
            opening_credit += gl.credit

        return opening_debit, opening_credit

    def get_duration_balances_from_gl():
        debit, credit = 0, 0
        q = """ SELECT 
                    name, debit, credit, posting_date  
                FROM  
                    `tabGL Entry` 
                WHERE 
                    account=%(account)s 
                AND 
                    is_cancelled = 0  
                AND 
                    (posting_date >= %(from_date)s AND posting_date <= %(to_date)s) 
        """
        gl_entries = frappe.db.sql(q, gl_filters, as_dict=True)

        for gl in gl_entries:
            debit += gl.debit
            credit += gl.credit

        return debit, credit

    section_data = {}
    for row in trial_balance_settings.get(child, []):
        if row.get("is_parent"):
            section_data[row.get("title")] = {
                "title": row.get("title"),
                "opening_debit": 0,
                "opening_credit": 0,
                "debit": 0,
                "credit": 0,
                "closing_debit": 0,
                "closing_credit": 0
            }
        else:
            gl_filters.update({
                "account": row.get("account")
            })
            # Get opening
            opening_debit, opening_credit = get_opening_balances_from_gl()
            # Get duration debit and credit
            debit, credit = get_duration_balances_from_gl()
            # Calculate closing balances
            closing_debit = opening_debit - debit
            closing_credit = opening_credit - credit
            section_data[row.get("title")] = {
                "title": row.get("title"),
                "opening_debit": opening_debit,
                "opening_credit": opening_credit,
                "debit": debit,
                "credit": credit,
                "closing_debit": closing_debit,
                "closing_credit": closing_credit
            }

            if row.get("parent1"):
                parent_record = section_data[row.get("parent1")]
                parent_record.update({
                    "opening_debit": parent_record["opening_debit"] + opening_debit,
                    "opening_credit": parent_record["opening_credit"] + opening_credit,
                    "debit": parent_record["debit"] + debit,
                    "credit": parent_record["credit"] + credit,
                    "closing_debit": parent_record["closing_debit"] + closing_debit,
                    "closing_credit": parent_record["closing_credit"] + closing_credit,
                })

    for section in section_data:
        result.append(section_data[section])


def get_customers_section_data(filters, trial_balance_settings, child, result):
    invfrm = frappe.qb.DocType("Invoice Form")
    invfrmitem = frappe.qb.DocType("Invoice Form Item")
    entry = frappe.qb.DocType("Payment Entry")
    docstatuses = [1]
    if filters.get("draft"):
        docstatuses.append(0)

    def get_customers_opening_balance():
        # get opening debit
        opening_debit_query = frappe.qb.from_(invfrm).join(invfrmitem).on(invfrmitem.parent == invfrm.name).select(
            Sum(invfrmitem.total).as_("total")).where(
            invfrm.company == filters.get("company")).where(
            invfrm.posting_date.lt(filters.get("from_date"))).where(
            invfrmitem.customer.isin(customers)).where(invfrm.docstatus.isin(docstatuses))

        opening_debit = opening_debit_query.run(as_dict=True)[0]["total"] or 0

        # get opening credit
        payments_query = frappe.qb.from_(entry).where(
            entry.company == filters.get('company')).where(
            entry.party.isin(customers)).where(
            entry.posting_date.lt(filters.get("from_date"))).where(entry.docstatus.isin(docstatuses))

        payments_query = payments_query.select(entry.payment_type).select(
            Case().when(entry.payment_type == "Receive", Sum(entry.paid_amount)).
            when(entry.payment_type == "Pay", (Sum(entry.paid_amount * -1))).
            else_(Sum(entry.paid_amount)).as_("paid_amount")
        )
        payments = payments_query.run(as_dict=True)

        opening_credit = sum([payment["paid_amount"] for payment in payments if payment["paid_amount"]]) or 0

        return opening_debit, opening_credit

    def get_customers_duration_balance():
        # get duration debit
        duration_debit_query = frappe.qb.from_(invfrm).join(invfrmitem).on(invfrmitem.parent == invfrm.name).select(
            Sum(invfrmitem.total).as_("total")).where(
            invfrm.company == filters.get("company")).where(
            invfrm.posting_date.gte(filters.get("from_date"))).where(
            invfrm.posting_date.lte(filters.get("to_date"))).where(
            invfrmitem.customer.isin(customers)).where(invfrm.docstatus.isin(docstatuses))

        duration_debit = duration_debit_query.run(as_dict=True)[0]["total"] or 0

        # get duration credit
        payments_query = frappe.qb.from_(entry).where(
            entry.company == filters.get('company')).where(
            entry.party.isin(customers)).where(
            entry.posting_date.gte(filters.get("from_date"))).where(
            entry.posting_date.lte(filters.get("to_date"))).where(
            entry.docstatus.isin(docstatuses))

        payments_query = payments_query.select(entry.payment_type).select(
            Case().when(entry.payment_type == "Receive", entry.paid_amount).
            when(entry.payment_type == "Pay", (entry.paid_amount * -1)).
            else_(entry.paid_amount).as_("paid_amount")
        )
        payments = payments_query.run(as_dict=True)

        duration_credit = sum([payment["paid_amount"] for payment in payments if payment["paid_amount"]]) or 0
        return duration_debit, duration_credit

    # get all customers under this group
    section_data = {}
    for row in trial_balance_settings.get(child, []):
        if row.get("is_parent"):
            section_data[row.get("title")] = {
                "title": row.get("title"),
                "opening_debit": 0,
                "opening_credit": 0,
                "debit": 0,
                "credit": 0,
                "closing_debit": 0,
                "closing_credit": 0
            }
        else:
            if row.get("customer_group"):
                customers = frappe.get_all("Customer",
                                           {"customer_group": row.get("customer_group"), "is_customer": 1},
                                           pluck="name")
                # get opening
                opening_debit, opening_credit = get_customers_opening_balance()

                # get duration
                debit, credit = get_customers_duration_balance()
                closing_debit = opening_debit - debit
                closing_credit = opening_credit - credit
                section_data[row.get("title")] = {
                    "title": row.get("title"),
                    "opening_debit": opening_debit,
                    "opening_credit": opening_credit,
                    "debit": debit,
                    "credit": credit,
                    "closing_debit": closing_debit,
                    "closing_credit": closing_credit
                }

                if row.get("parent1"):
                    parent_record = section_data[row.get("parent1")]
                    parent_record.update({
                        "opening_debit": parent_record["opening_debit"] + opening_debit,
                        "opening_credit": parent_record["opening_credit"] + opening_credit,
                        "debit": parent_record["debit"] + debit,
                        "credit": parent_record["credit"] + credit,
                        "closing_debit": parent_record["closing_debit"] + closing_debit,
                        "closing_credit": parent_record["closing_credit"] + closing_credit,
                    })
    for section in section_data:
        result.append(section_data[section])


def get_suppliers_section_data(filters, trial_balance_settings, child, result):
    invfrm = frappe.qb.DocType("Invoice Form")
    entry = frappe.qb.DocType("Payment Entry")
    docstatuses = [1]
    if filters.get("draft"):
        docstatuses.append(0)

    def get_suppliers_opening_balance():
        # get opening debit
        opening_debit_query = frappe.qb.from_(invfrm).select(Sum(invfrm.grand_total).as_("total")).where(
            invfrm.company == filters.get("company")).where(
            invfrm.posting_date.lt(filters.get("from_date"))).where(
            invfrm.supplier.isin(suppliers))

        opening_debit_query = opening_debit_query.where(invfrm.docstatus.isin(docstatuses))
        opening_debit = opening_debit_query.run(as_dict=True)[0]["total"] or 0

        # get opening credit
        payments_query = frappe.qb.from_(entry).where(
            entry.company == filters.get('company')).where(
            entry.party.isin(suppliers)).where(
            entry.posting_date.lt(filters.get("from_date"))).where(
            entry.docstatus.isin(docstatuses))

        payments_query = payments_query.select(entry.payment_type).select(
            Case().when(entry.payment_type == "Pay", Sum(entry.paid_amount)).
            when(entry.payment_type == "Receive", (Sum(entry.paid_amount * -1))).
            else_(Sum(entry.paid_amount)).as_("paid_amount")
        )
        payments = payments_query.run(as_dict=True)

        opening_credit = sum([payment["paid_amount"] for payment in payments if payment["paid_amount"]]) or 0

        return opening_debit, opening_credit

    def get_suppliers_duration_balance():
        # get duration debit
        duration_debit_query = frappe.qb.from_(invfrm).select(Sum(invfrm.grand_total).as_("total")).where(
            invfrm.company == filters.get("company")).where(
            invfrm.posting_date.gte(filters.get("from_date"))).where(
            invfrm.posting_date.lte(filters.get("to_date"))).where(
            invfrm.supplier.isin(suppliers))

        duration_debit_query = duration_debit_query.where(invfrm.docstatus.isin(docstatuses))
        duration_debit = duration_debit_query.run(as_dict=True)[0]["total"] or 0

        # get duration credit
        payments_query = frappe.qb.from_(entry).where(
            entry.company == filters.get('company')).where(
            entry.party.isin(suppliers)).where(
            entry.posting_date.gte(filters.get("from_date"))).where(
            entry.posting_date.lte(filters.get("to_date"))).where(
            entry.docstatus.isin(docstatuses))

        payments_query = payments_query.select(entry.payment_type).select(
            Case().when(entry.payment_type == "Pay", entry.paid_amount).
            when(entry.payment_type == "Receive", (entry.paid_amount * -1)).
            else_(entry.paid_amount).as_("paid_amount")
        )
        payments = payments_query.run(as_dict=True)

        duration_credit = sum([payment["paid_amount"] for payment in payments if payment["paid_amount"]]) or 0
        return duration_debit, duration_credit

    # get all suppliers under this group
    section_data = {}
    for row in trial_balance_settings.get(child, []):
        if row.get("is_parent"):
            section_data[row.get("title")] = {
                "title": row.get("title"),
                "opening_debit": 0,
                "opening_credit": 0,
                "debit": 0,
                "credit": 0,
                "closing_debit": 0,
                "closing_credit": 0
            }
        else:
            if row.get("supplier_group"):
                suppliers = frappe.get_all("Supplier", {"supplier_group": row.get("supplier_group")}, pluck="name")
                # get opening
                opening_debit, opening_credit = get_suppliers_opening_balance()

                # get duration
                debit, credit = get_suppliers_duration_balance()
                closing_debit = opening_debit - debit
                closing_credit = opening_credit - credit
                section_data[row.get("title")] = {
                    "title": row.get("title"),
                    "opening_debit": opening_debit,
                    "opening_credit": opening_credit,
                    "debit": debit,
                    "credit": credit,
                    "closing_debit": closing_debit,
                    "closing_credit": closing_credit
                }

                if row.get("parent1"):
                    parent_record = section_data[row.get("parent1")]
                    parent_record.update({
                        "opening_debit": parent_record["opening_debit"] + opening_debit,
                        "opening_credit": parent_record["opening_credit"] + opening_credit,
                        "debit": parent_record["debit"] + debit,
                        "credit": parent_record["credit"] + credit,
                        "closing_debit": parent_record["closing_debit"] + closing_debit,
                        "closing_credit": parent_record["closing_credit"] + closing_credit,
                    })
    for section in section_data:
        result.append(section_data[section])


def get_taxes_section_data(filters, trial_balance_settings, child, result):
    invfrm = frappe.qb.DocType("Invoice Form")
    invfrmcom = frappe.qb.DocType("Invoice Form Commission")
    docstatuses = [1]
    if filters.get("draft"):
        docstatuses.append(0)

    def get_taxes_opening_balance():
        commission = frappe.qb.from_(invfrm).join(invfrmcom).on(invfrmcom.parent == invfrm.name).select(
            ((invfrmcom.price * invfrmcom.commission) / 100).as_("total_commission")).where(
            invfrm.company == filters.get("company")).where(
            invfrm.posting_date.lt(filters.get("from_date"))).where(invfrm.docstatus.isin(docstatuses)).run(
            as_dict=True)

        total_commission = sum([com["total_commission"] for com in commission])
        opening_debit = (total_commission * 15) / 100
        return opening_debit, 0

    def get_taxes_duration_balance():
        commission = frappe.qb.from_(invfrm).join(invfrmcom).on(invfrmcom.parent == invfrm.name).select(
            ((invfrmcom.price * invfrmcom.commission) / 100).as_("total_commission")).where(
            invfrm.company == filters.get("company")).where(
            invfrm.posting_date.gte(filters.get("from_date"))).where(
            invfrm.posting_date.lte(filters.get("to_date"))).where(invfrm.docstatus.isin(docstatuses)).run(as_dict=True)

        total_commission = sum([com["total_commission"] for com in commission])
        debit = (total_commission * 15) / 100
        return debit, 0

    section_data = {}
    for row in trial_balance_settings.get(child, []):
        if row.get("is_parent"):
            section_data[row.get("title")] = {
                "title": row.get("title"),
                "opening_debit": 0,
                "opening_credit": 0,
                "debit": 0,
                "credit": 0,
                "closing_debit": 0,
                "closing_credit": 0
            }
        else:
            opening_debit, opening_credit = get_taxes_opening_balance()
            debit, credit = get_taxes_duration_balance()
            closing_debit = opening_debit - debit
            closing_credit = opening_credit - credit
            section_data[row.get("title")] = {
                "title": row.get("title"),
                "opening_debit": opening_debit,
                "opening_credit": opening_credit,
                "debit": debit,
                "credit": credit,
                "closing_debit": closing_debit,
                "closing_credit": closing_credit
            }

            if row.get("parent1"):
                parent_record = section_data[row.get("parent1")]
                parent_record.update({
                    "opening_debit": parent_record["opening_debit"] + opening_debit,
                    "opening_credit": parent_record["opening_credit"] + opening_credit,
                    "debit": parent_record["debit"] + debit,
                    "credit": parent_record["credit"] + credit,
                    "closing_debit": parent_record["closing_debit"] + closing_debit,
                    "closing_credit": parent_record["closing_credit"] + closing_credit,
                })
    for section in section_data:
        result.append(section_data[section])


def get_columns():
    return [
        {
            "fieldname": "title",
            "label": _("Title"),
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "opening_debit",
            "label": _("Opening (Dr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "opening_credit",
            "label": _("Opening (Cr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "fieldname": "debit",
            "label": _("Debit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150
        },
        {
            "fieldname": "credit",
            "label": _("Credit"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150
        },
        {
            "fieldname": "closing_debit",
            "label": _("Closing (Dr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150
        },
        {
            "fieldname": "closing_credit",
            "label": _("Closing (Cr)"),
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150
        }
    ]
