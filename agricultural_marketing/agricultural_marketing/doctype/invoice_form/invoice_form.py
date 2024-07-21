# Copyright (c) 2024, Muhammad Salama and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class InvoiceForm(Document):
	def on_update(self):
		self.update_grand_total()

	def update_grand_total(self):
		self.grand_total = 0
		for item in self.items:
			self.grand_total += item.total