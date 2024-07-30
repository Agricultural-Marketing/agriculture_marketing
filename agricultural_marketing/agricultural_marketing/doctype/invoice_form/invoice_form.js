// Copyright (c) 2024, Muhammad Salama and contributors
// For license information, please see license.txt

frappe.ui.form.on("Invoice Form", {
 	refresh(frm) {
     	filter_basic_info_fields(frm);
     	filter_child_tables_fields(frm);

 	}
});

frappe.ui.form.on("Invoice Form Item", {
    items_add: function (frm, cdt, dcn) {
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
    frm.set_query("supplier", function () {
			return {
				filters: {
					is_farmer: 1,
				},
			};
		});

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
    frm.fields_dict['items'].grid.get_field("customer").get_query = function() {
            return {
                filters: {
                    name: ["in", [frm.doc.customer, frm.doc.pamper]]
                }
            }
        };
    frm.fields_dict['items'].grid.get_field("pamper").get_query = function() {
        return {
            filters: {
                name: ["in", [frm.doc.pamper]]
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