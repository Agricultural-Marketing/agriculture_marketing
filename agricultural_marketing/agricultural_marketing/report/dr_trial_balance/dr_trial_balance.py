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
    sections = ["cash_section", "customers_section", "suppliers_section", "share_capital_section", "taxes_section",
                "income_section", "expense_section"]
    for section in sections:
        for row in trial_balance_settings.get(section, []):
            if not row.get("is_parent"):
                gl_filters.update({
                    "account": row.get("account")
                })
                # Get opening
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

                # Get debit and credit
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
                        ((posting_date >= %(from_date)s AND posting_date <= %(to_date)s) OR is_opening = 'Yes') 
                """
                gl_entries = frappe.db.sql(q, gl_filters, as_dict=True)

                for gl in gl_entries:
                    debit += gl.debit
                    credit += gl.credit

                result.append({
                    "title": row.get("title"),
                    "opening_debit": opening_debit,
                    "opening_credit": opening_credit,
                    "debit": debit,
                    "credit": credit,
                    "closing_debit": opening_debit - debit,
                    "closing_credit": opening_credit - credit,
                })
    return result


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
