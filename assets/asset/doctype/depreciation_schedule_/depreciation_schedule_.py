# Copyright (c) 2021, Ganga Manoj and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_months, date_diff, add_days, getdate


class DepreciationSchedule_(Document):
	def validate(self):
		from assets.controllers.base_asset import validate_serial_no

		validate_serial_no(self)

	def before_submit(self):
		self.set_status("Active")

	def set_status(self, status):
		self.db_set("status", status)

def create_depreciation_schedules(asset, date_of_sale=None):
	purchase_value, opening_accumulated_depr = get_depr_details(asset)

	for row in asset.get('finance_books'):
		depr_schedule = frappe.new_doc("Depreciation Schedule_")

		if asset.doctype == "Asset_":
			depr_schedule.asset = asset.name
		else:
			depr_schedule.asset = asset.asset
			depr_schedule.serial_no = asset.serial_no

		depr_schedule.creation_date = getdate()
		depr_schedule.finance_book = row.finance_book

		make_depreciation_schedule(depr_schedule, asset, row, purchase_value, opening_accumulated_depr, date_of_sale)

		depr_schedule.save()

def get_depr_details(asset):
	if asset.doctype == "Asset_":
		return asset.gross_purchase_amount, asset.opening_accumulated_depreciation
	else:
		purchase_value, opening_accumulated_depr = frappe.get_value(
			"Asset_",
			asset.asset,
			["gross_purchase_amount", "opening_accumulated_depreciation"]
		)

		return purchase_value, opening_accumulated_depr

def make_depreciation_schedule(depr_schedule, asset, finance_book, purchase_value, opening_accumulated_depr, date_of_sale):
	depreciable_value = purchase_value - finance_book.salvage_value

	depr_method, frequency_of_depr, asset_life, asset_life_unit = frappe.get_value(
		"Depreciation Template",
		finance_book.depreciation_template,
		["depreciation_method", "frequency_of_depreciation", "asset_life", "asset_life_unit"]
	)

	if depr_method == "Straight Line":
		frequency_of_depr = get_frequency_of_depreciation_in_months(frequency_of_depr)
		asset_life = get_asset_life_in_months(asset_life, asset_life_unit)

		depr_in_one_day = get_depreciation_in_one_day(asset.available_for_use_date, asset_life, depreciable_value)

		depr_start_date = get_depreciation_start_date(asset.available_for_use_date, opening_accumulated_depr, depr_in_one_day)
		depr_end_date = get_depreciation_end_date(asset.available_for_use_date, asset_life, date_of_sale)

		schedule_date = finance_book.depreciation_posting_start_date

		while schedule_date < depr_end_date:
			create_depreciation_entry(depr_schedule, schedule_date, depr_start_date, depr_in_one_day)

			depr_start_date = add_days(schedule_date, 1)
			schedule_date = add_months(schedule_date, frequency_of_depr)

		# for the final row
		create_depreciation_entry(depr_schedule, depr_end_date, depr_start_date, depr_in_one_day)

def get_frequency_of_depreciation_in_months(frequency_of_depreciation):
	frequency_in_months = {
		"Monthly": 1,
		"Every 2 months": 2,
		"Quarterly": 3,
		"Every 4 months": 4,
		"Every 5 months": 5,
		"Half-Yearly": 6,
		"Every 7 months": 7,
		"Every 8 months": 8,
		"Every 9 months": 9,
		"Every 10 months": 10,
		"Every 11 months": 11,
		"Yearly": 12
	}

	return frequency_in_months[frequency_of_depreciation]

def get_asset_life_in_months(asset_life, asset_life_unit):
	if asset_life_unit == "Months":
		return asset_life
	else:
		return (asset_life * 12)

def get_depreciation_start_date(available_for_use_date, opening_accumulated_depr, depr_in_one_day):
	if not opening_accumulated_depr:
		return available_for_use_date
	else:
		days_of_depr_booked = int(opening_accumulated_depr / depr_in_one_day)
		return add_days(available_for_use_date, days_of_depr_booked)

def get_depreciation_end_date(available_for_use_date, asset_life, date_of_sale):
	if date_of_sale:
		return date_of_sale

	day_after_depr_end_date = add_months(available_for_use_date, asset_life)
	depr_end_date = add_days(day_after_depr_end_date, -1)

	return depr_end_date

def get_depreciation_in_one_day(available_for_use_date, asset_life, depreciable_value):
	depr_end_date = add_months(available_for_use_date, asset_life)
	asset_life_in_days = date_diff(depr_end_date, available_for_use_date)

	return depreciable_value / asset_life_in_days

def create_depreciation_entry(depr_schedule, schedule_date, depr_start_date, depr_in_one_day):
	depr_period = date_diff(schedule_date, depr_start_date) + 1
	depr_amount = depr_in_one_day * depr_period

	if depr_amount > 0:
		depr_schedule.append("depreciation_schedule", {
			"schedule_date": schedule_date,
			"depreciation_amount": depr_amount
		})