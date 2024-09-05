frappe.pages['statement-forms'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Statement Forms'),
		single_column: true
	});

    let company = page.add_field({
	    label: 'Company',
	    fieldtype: 'Link',
	    fieldname: 'company',
	    default: frappe.defaults.get_default("company")
	});
    company.$wrapper.removeClass('col-md-2').addClass('col-md-4');


    let fromDate = page.add_field({
	    label: 'From Date',
	    fieldtype: 'Date',
	    fieldname: 'from_date'
	});
    fromDate.$wrapper.removeClass('col-md-2').addClass('col-md-4');

	let toDate = page.add_field({
	    label: 'To Date',
	    fieldtype: 'Date',
	    fieldname: 'to_date'
	});
    toDate.$wrapper.removeClass('col-md-2').addClass('col-md-4');

	let partyTypeField = page.add_field({
	    label: 'Party Type',
	    fieldtype: 'Link',
	    fieldname: 'party_type',
	    options: 'DocType',
	    reqd: 1,
	    get_query: function() {
	        return {
	            filters: {
	                name: ['in', ['Customer', 'Supplier']],
	            }
	        }
	    },
	    change() {
	        let partyField;
            if (!partyTypeField.get_value()) {
                partyField = page.fields_dict['party']
                if (partyField) {
                    partyField.set_value("");
                    partyField.$wrapper.hide();
                }
            } else {
                partyField = page.fields_dict['party']
                if (!partyField) {
                    partyField = page.add_field({
                        label: 'Party',
                        fieldtype: 'Link',
                        fieldname: 'party'
                    });
                    partyField.$wrapper.removeClass('col-md-2').addClass('col-md-4');
                }
                if (partyField) {
                    partyField.set_value("");
                    partyField.$wrapper.show();
                    partyField.df.options = partyTypeField.get_value();
                    partyField.df.get_query = () => {
                        if (partyTypeField.get_value() == 'Customer') {
                            return {
                                filters: {
                                    is_customer: 1,
                                }
                            }
                        }
                    }
                }
            }
	    }
	});
    partyTypeField.$wrapper.removeClass('col-md-2').addClass('col-md-4');

function get_reports(filters) {
        frappe.dom.freeze("Processing...");
        var final_filters = {};
        for (let key in filters) {
            final_filters[key] = filters[key].value;
        }
        if (!final_filters['party_type']) {
            frappe.dom.unfreeze();
            frappe.throw(__("Party Type is required"));
        }
        frappe.call({
            method: "agricultural_marketing.agricultural_marketing.page.statement_forms.statement_forms.get_reports",
            args : {
                filters: final_filters
            },
            callback: function (r) {
                if (r.message) {
                    downloadFiles(r.message);
                    frappe.dom.unfreeze();
                }
            },
        });
    }

async function downloadFiles(file_urls) {
    for (const file_url of file_urls) {
        await new Promise((resolve) => {
            open_url_post(frappe.request.url, {
                cmd: "frappe.core.doctype.file.file.download_file",
                file_url: file_url,
            });
            setTimeout(resolve, 1000);  // Wait for 3 second before downloading the next file
        });
    }
}

let $btn = page.set_primary_action( __("Download Reports"), () => { get_reports(page.fields_dict) });
}