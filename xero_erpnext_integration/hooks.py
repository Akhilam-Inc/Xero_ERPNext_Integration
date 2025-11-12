
app_name = "xero_erpnext_integration"
app_title = "Xero Erpnext Integration"
app_publisher = "nasirucode"
app_description = "Xero Erpnext Integration"
app_email = "akingbolahan12@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "xero_erpnext_integration",
# 		"logo": "/assets/xero_erpnext_integration/logo.png",
# 		"title": "Xero Erpnext Integration",
# 		"route": "/xero_erpnext_integration",
# 		"has_permission": "xero_erpnext_integration.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/xero_erpnext_integration/css/xero_erpnext_integration.css"
# app_include_js = "/assets/xero_erpnext_integration/js/xero_erpnext_integration.js"

# include js, css files in header of web template
# web_include_css = "/assets/xero_erpnext_integration/css/xero_erpnext_integration.css"
# web_include_js = "/assets/xero_erpnext_integration/js/xero_erpnext_integration.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "xero_erpnext_integration/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {
    "Contact" : "xero_erpnext_integration/custom_scripts/contact.js",
    "Sales Invoice" : "xero_erpnext_integration/custom_scripts/sales_invoice.js",
    "Payment Entry": "xero_erpnext_integration/custom_scripts/payment_entry.js"
}

scheduler_events = {
    "cron": {
		"0 */2 * * *":  [
			"xero_erpnext_integration.xero_erpnext_integration.apis.sales_invoice.sync_invoice_payments"
		],
		"*/30 * * * *": [
			"xero_erpnext_integration.xero_erpnext_integration.schedulers.voided_invoice_sync.sync_voided_invoices"
		]
	},
}

# Document Events
doc_events = {
    "Sales Invoice": {
        # "on_submit": "xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice.on_submit",
        "on_cancel": "xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice.on_cancel",
        # "before_submit": "xero_erpnext_integration.xero_erpnext_integration.custom_scripts.sales_invoice.before_submit",
    }
}

fixtures = [
   {
       "doctype": "Custom Field",
       "filters": [["module", "=", "Xero Erpnext Integration"]]
   },
   {
       "doctype": "Property Setter",
       "filters": [["module", "=", "Xero Erpnext Integration"]]
   }
]

# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "xero_erpnext_integration/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "xero_erpnext_integration.utils.jinja_methods",
# 	"filters": "xero_erpnext_integration.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "xero_erpnext_integration.install.before_install"
# after_install = "xero_erpnext_integration.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "xero_erpnext_integration.uninstall.before_uninstall"
# after_uninstall = "xero_erpnext_integration.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "xero_erpnext_integration.utils.before_app_install"
# after_app_install = "xero_erpnext_integration.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "xero_erpnext_integration.utils.before_app_uninstall"
# after_app_uninstall = "xero_erpnext_integration.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "xero_erpnext_integration.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"xero_erpnext_integration.tasks.all"
# 	],
# 	"daily": [
# 		"xero_erpnext_integration.tasks.daily"
# 	],
# 	"hourly": [
# 		"xero_erpnext_integration.tasks.hourly"
# 	],
# 	"weekly": [
# 		"xero_erpnext_integration.tasks.weekly"
# 	],
# 	"monthly": [
# 		"xero_erpnext_integration.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "xero_erpnext_integration.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "xero_erpnext_integration.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "xero_erpnext_integration.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["xero_erpnext_integration.utils.before_request"]
# after_request = ["xero_erpnext_integration.utils.after_request"]

# Job Events
# ----------
# before_job = ["xero_erpnext_integration.utils.before_job"]
# after_job = ["xero_erpnext_integration.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"xero_erpnext_integration.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

