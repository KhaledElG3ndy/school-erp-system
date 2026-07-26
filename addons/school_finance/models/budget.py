from odoo import api, models


class CrossoveredBudget(models.Model):
    _name = "crossovered.budget"
    _inherit = ["crossovered.budget", "school.finance.approval.mixin"]

    @api.depends(
        "company_id",
        "company_id.school_require_budget_approval",
    )
    def _compute_school_approval_required(self):
        return super()._compute_school_approval_required()

    def _school_requires_approval(self):
        self.ensure_one()
        return self.company_id.school_require_budget_approval

    def action_budget_validate(self):
        self._school_check_approved()
        return super().action_budget_validate()
