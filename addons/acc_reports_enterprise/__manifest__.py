{
    "name": "Accounting Reports Enterprise Simulation",
    "summary": "Open community accounting reports in an enterprise-style HTML view with PDF and XLSX export.",
    "version": "19.0.1.0.18",
    "category": "Accounting",
    "author": "Custom",
    "website": "https://www.odoo.com",
    "license": "LGPL-3",
    "depends": [
        "web",
        "account",
        "accounting_pdf_reports",
        "om_account_accountant",
        "om_account_asset",
        "om_account_daily_reports",
    ],
    "data": [
        "security/ir.model.access.csv",
        "report/report_common_templates.xml",
        "report/report_financial_templates.xml",
        "report/report_cash_flow_templates.xml",
        "report/report_executive_summary_templates.xml",
        "data/balance_sheet_hierarchy.xml",
        "data/report_type_override.xml",
        "data/menu_action_override.xml",
        "data/invoice_analysis_override.xml",
        "data/analytic_reporting_override.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "acc_reports_enterprise/static/src/scss/report_preview.scss",
            "acc_reports_enterprise/static/src/xml/report_client_action.xml",
            "acc_reports_enterprise/static/src/js/report_client_action.js"
        ],
        "web.assets_backend_lazy": [
            "acc_reports_enterprise/static/src/js/pivot_negative_values.js",
        ]
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "post_init_hook": "set_account_report_html_actions"
}
