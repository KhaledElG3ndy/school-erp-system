from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountAssetAsset(models.Model):
    _name = "account.asset.asset"
    _inherit = ["account.asset.asset", "school.finance.approval.mixin"]

    school_department_id = fields.Many2one(
        "school.department", string="Department / Cost Center", check_company=True
    )
    school_asset_location = fields.Char(string="Asset Location", tracking=True)
    school_custodian_id = fields.Many2one(
        "res.partner", string="Asset Custodian", tracking=True
    )
    school_disposal_type = fields.Selection(
        [
            ("sale", "Sale"),
            ("scrap", "Scrap"),
            ("donation", "Donation"),
            ("other", "Other"),
        ],
        string="Disposal Type",
        tracking=True,
    )
    school_disposal_reason = fields.Text(string="Disposal Reason", tracking=True)
    school_disposal_proceeds = fields.Monetary(
        string="Disposal Proceeds", currency_field="currency_id", tracking=True
    )

    @api.depends(
        "company_id",
        "company_id.school_require_asset_disposal_approval",
        "school_disposal_type",
    )
    def _compute_school_approval_required(self):
        return super()._compute_school_approval_required()

    def _school_requires_approval(self):
        self.ensure_one()
        return bool(
            self.school_disposal_type
            and self.company_id.school_require_asset_disposal_approval
        )

    def set_to_close(self):
        missing = self.filtered(
            lambda asset: not asset.school_disposal_type
            or not asset.school_disposal_reason
        )
        if missing:
            raise UserError(
                _("Enter the disposal type and reason before selling or disposing an asset.")
            )
        self._school_check_approved()
        return super().set_to_close()
