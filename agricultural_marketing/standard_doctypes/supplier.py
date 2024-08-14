import frappe


def create_related_customer(self, method):
    related_customer = frappe.new_doc("Customer")
    related_customer.update(
        {"customer_name": self.supplier_name,
         "customer_group": "All Customer Groups",
         "is_farmer": 1,
         "commission_percentage": self.commission_percentage
         }
    )

    related_customer.insert(ignore_permissions=True)
    self.db_set("related_customer", related_customer.name)
    self.db_set("related_customer_group", related_customer.customer_group)


def delete_related_customer(self, method):
    customer = frappe.qb.DocType("Customer")
    frappe.qb.from_(customer).where(customer.name == self.related_customer).delete().run()
