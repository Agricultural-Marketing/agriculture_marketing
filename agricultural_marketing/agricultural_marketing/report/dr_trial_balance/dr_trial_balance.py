# Copyright (c) 2025, Muhammad Salama and contributors
# For license information, please see license.txt

import frappe
from frappe import _


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
    children = ["cash_section", "customers_section", "suppliers_section", "share_capital_section", "taxes_section",
                "income_section", "expense_section"]
    for child in children:
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
                    "closing_credit": 0,
                    "is_parent": 1
                }
            else:
                gl_filters.update({
                    "account": row.get("account")
                })
                # Get opening
                opening_debit, opening_credit = get_opening_balances_from_gl(gl_filters)
                # Get duration debit and credit
                debit, credit = get_duration_balances_from_gl(gl_filters)
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
                    "closing_credit": closing_credit,
                    "is_parent": 0
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

    return result


def get_opening_balances_from_gl(gl_filters):
    opening_debit, opening_credit = 0, 0
    q = """ 
                        SELECT 
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


def get_duration_balances_from_gl(gl_filters):
    debit, credit = 0, 0
    q = """ 
                        SELECT 
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
        },
        {
            "fieldname": "is_parent",
            "label": _("IS Parent"),
            "fieldtype": "Check",
            "width": 50
        }
    ]
