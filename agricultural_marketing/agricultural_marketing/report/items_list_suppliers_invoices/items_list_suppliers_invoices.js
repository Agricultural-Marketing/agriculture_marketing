// Copyright (c) 2024, Muhammad Salama and contributors
// For license information, please see license.txt

frappe.query_reports["Items list suppliers invoices"] = {
	"filters": [
	    {
           "fieldname": "supplier",
           "fieldtype": "Link",
           "label": "Supplier",
           "options": "Supplier",
           "wildcard_filter": 0
        },
	    {
           "fieldname": "invoice_id",
           "fieldtype": "Data",
           "label": "Invoice No",
           "wildcard_filter": 0
       },
       {
           "fieldname": "item_code",
           "fieldtype": "Data",
           "label": "Item",
           "wildcard_filter": 0
       },
       {
           "fieldname": "from_date",
           "fieldtype": "Date",
           "label": "From Date",
           "wildcard_filter": 0
       },
       {
           "fieldname": "to_date",
           "fieldtype": "Date",
           "label": "To Date",
           "wildcard_filter": 0
       },
	]
};
