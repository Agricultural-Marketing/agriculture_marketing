// Copyright (c) 2024, Muhammad Salama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Invoice Form", {
 	refresh(frm) {
     	filter_basic_info_fields(frm);
     	filter_child_tables_fields(frm);
     	frm.add_custom_button("Print", () => {
     	    let dialog = new frappe.ui.Dialog({
     	        title: "Print options",
     	        fields: [
     	            {
                        label: 'Party Type',
                        fieldname: 'party_type',
                        fieldtype: 'Link',
                        options: "DocType",
                        get_query: function () {
                            return {
                                filters: {
                                    name: ["in", ["Supplier", "Customer"]]
                                },
                            };
					    },
					    onchange: function () {
    					    let field = dialog.fields_dict["party_type"];
    					    if (field.value) {
							    dialog.set_df_property("party", "options", field.value);
                                dialog.set_df_property("party", "hidden", 0);
                                dialog.set_df_property("party", "get_query", get_query(frm, field.value));
    					    } else {
							    dialog.set_df_property("party", "options", "Supplier");
                                dialog.set_df_property("party", "hidden", 1);
    					    }
						},
                    },
                    {
                        label: 'Party',
                        fieldname: 'party',
                        fieldtype: 'Link',
                        hidden: 1,
                    },
     	        ],
     	        size: "small",
     	        primary_action_label: 'Print',
                primary_action(values) {
                    values['reference_doctype'] = frm.doc.doctype
                    values['reference_name'] = frm.doc.name
                    dialog.hide();
        			window.open(`/api/method/agricultural_marketing.pdf.get_pdf?filters={"reference_doctype": "${values.reference_doctype}", "reference_name": "${values.reference_name}", "party_type": "${values.party_type}", "party": "${values.party}"}&template=invoice_form&doctype=invoice_form`);
                }
     	    });
     	    dialog.show();
        })
 	},
 	customer: function (frm, cdt, cdn) {
 	    frm.doc.items.forEach((row)=> {
 	        row.customer = frm.doc.customer;
 	        frm.refresh_field("items");
 	    });
 	},
    pamper: function (frm, cdt, cdn) {
        frm.doc.items.forEach((row)=> {
 	        row.pamper = frm.doc.pamper;
 	        frm.refresh_field("items");
 	    });
 	},
});

frappe.ui.form.on("Invoice Form Item", {
    items_add: function (frm, cdt, cdn) {
        let row = frm.selected_doc;
        row.pamper = frm.doc.pamper;
        row.customer = frm.doc.customer;
        frm.refresh_field('items');
    },
    qty: function (frm, cdt, cdn) {
        calculate_total_line(frm);
    },
    price: function (frm, cdt, cdn) {
        calculate_total_line(frm);
    }
});

frappe.ui.form.on("Invoice Form Commission", {
    commission: function (frm, cdt, cdn) {
        calculate_total_commission_line(frm);
    },
    taxes: function (frm, cdt, cdn) {
        calculate_total_commission_line(frm);
    }
});


frappe.ui.form.on("Invoice Form Pamper Commission", {
    price: function (frm, cdt, cdn) {
        calculate_commission(frm);
    },
    percentage: function (frm, cdt, cdn) {
        calculate_commission(frm);
    }
});


function filter_basic_info_fields(frm) {
    frm.set_query("customer", function () {
        return {
            filters: {
                is_customer: 1,
            },
        };
    });

    frm.set_query("pamper", function () {
        return {
            filters: {
                is_pamper: 1,
            },
        };
    });
}

function filter_child_tables_fields(frm) {
    var customers = [];
    frappe.db.get_list("Customer", {
        filters: {"is_customer": 1},
        fields: ["name"]
    })
    .then((result) => {
            result.forEach((cus) => customers.push(cus.name))
    });
    frm.fields_dict['items'].grid.get_field("customer").get_query = function() {
            return {
                filters: {
                    name: ["in", customers]
                }
            }
    };
    var pampers = [];
    frappe.db.get_list("Customer", {
        filters: {"is_pamper": 1},
        fields: ["name"]
    })
    .then((result) => {
            result.forEach((pmp) => pampers.push(pmp.name))
    });
    frm.fields_dict['items'].grid.get_field("pamper").get_query = function() {
        return {
            filters: {
                name: ["in", pampers]
            }
        }
    };
    frm.fields_dict['items'].grid.get_field("item_code").get_query = function() {
        return {
            filters: {
                commission_item: 0
            }
        }
    };
    frm.fields_dict['commissions'].grid.get_field("item").get_query = function() {
        return {
            filters: {
                commission_item: 1
            }
        }
    };
    frm.fields_dict['pamper_commissions'].grid.get_field("pamper").get_query = function() {
        return {
            filters: {
                name: ["in", [frm.doc.pamper]]
            }
        }
    }
}

function calculate_total_line(frm) {
    let row = frm.selected_doc;
    row.qty = (row.qty) ? row.qty: 0;
    row.price = (row.price) ? row.price: 0;
    row.total = row.qty * row.price;
    frm.refresh_field('items');
}

function calculate_total_commission_line(frm) {
    let row = frm.selected_doc;
    row.taxes = (row.taxes) ? row.taxes: 0;
    row.commission = (row.commission) ? row.commission: 0;
    row.commission_total = row.commission + row.taxes;
    frm.refresh_field('commissions');
}

function calculate_commission(frm) {
    let row = frm.selected_doc;
    row.price = (row.price) ? row.price: 0;
    row.percentage = (row.percentage) ? row.percentage: 0;
    row.commission = (row.price * row.percentage) / 100;
    frm.refresh_field('pamper_commissions');
}

let get_query = function (frm, doctype) {
    result = []
    if (doctype == "Supplier") {
        result.push(frm.doc.supplier);
    } else {
        let rows = frm.doc.items;
        for (var i=0; i<rows.length; i++) {
            if (!result.includes(rows[i].customer)) {
                result.push(rows[i].customer)
            }
        }
    }
    return {
        filters: {
            name: ["in", result]
        },
    };
}