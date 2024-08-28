import json
import os

import frappe
from frappe import _
from frappe.utils.pdf import get_pdf as _get_pdf
from agricultural_marketing.agricultural_marketing.doctype.invoice_form.invoice_form import build_pdf_template_context


@frappe.whitelist()
def get_pdf(filters, template, doctype, orientation="Landscape"):
    # FIXME: There is an issue in generated pdf filename
    # FIXME: Handle this method to be standalone can be used for any template not only invoice form
    if isinstance(filters, str):
        filters_j = json.loads(filters)

    filters = frappe._dict(filters_j)

    template_filename = os.path.join(template + '.html')
    folder = os.path.dirname(frappe.get_module("agricultural_marketing" + "." + "agricultural_marketing" +
                                               "." + "doctype").__file__)
    doctype_path = os.path.join(folder, doctype)
    paths_temp = os.path.join(doctype_path, template_filename)
    if not os.path.exists(doctype_path):
        frappe.throw(_("No template found for this doctype"))

    html_format = frappe.utils.get_html_format(paths_temp)

    res = build_pdf_template_context(filters)

    context = {"data": res, "filters": filters}
    html = frappe.render_template(html_format, context)

    # We do not use frappe's report_to_pdf function because it generates an access log with the actual PDF contents
    # in the database. That's unnecessary in this case
    frappe.local.response.filename = f"{filters.get('reference_name')}.pdf"
    frappe.local.response.filecontent = _get_pdf(html, {"orientation": orientation,
                                                        "title": f"{filters.get('reference_name')}.pdf"})
    frappe.local.response.type = "pdf"
