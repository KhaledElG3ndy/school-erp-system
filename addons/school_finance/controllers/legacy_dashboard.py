from odoo import http
from odoo.http import request


class SchoolFinanceLegacyDashboardRedirect(http.Controller):
    @http.route(
        [
            "/odoo/action-470",
            "/odoo/action-470/<path:legacy_path>",
        ],
        type="http",
        auth="user",
        readonly=True,
        methods=["GET"],
    )
    def legacy_dashboard_redirect(self, legacy_path=None, **kwargs):
        action = request.env.ref(
            "school_finance.action_school_accounting_overview"
        )
        return request.redirect(f"/odoo/action-{action.id}", 303)
