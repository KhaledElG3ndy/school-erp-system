from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    school_prevent_self_approval = fields.Boolean(
        string="Prevent Self Approval", default=True
    )
    school_require_entry_approval = fields.Boolean(
        string="Require Journal Entry Approval"
    )
    school_require_vendor_bill_approval = fields.Boolean(
        string="Require Vendor Bill Approval"
    )
    school_require_vendor_payment_approval = fields.Boolean(
        string="Require Vendor Payment Approval"
    )
    school_require_student_receipt_approval = fields.Boolean(
        string="Require Student Receipt Approval"
    )
    school_require_student_refund_approval = fields.Boolean(
        string="Require Student Refund Approval"
    )
    school_require_budget_approval = fields.Boolean(
        string="Require Budget Approval"
    )
    school_require_asset_disposal_approval = fields.Boolean(
        string="Require Asset Disposal Approval"
    )
    school_prevent_duplicate_student_fees = fields.Boolean(
        string="Block Duplicate Student Fees", default=True
    )
    school_prevent_duplicate_payment_reference = fields.Boolean(
        string="Block Duplicate Payment References", default=True
    )
    school_cash_negative_policy = fields.Selection(
        [
            ("allow", "Allow"),
            ("warn", "Warn in Chatter"),
            ("block", "Block"),
        ],
        string="Negative Cash Balance Policy",
        required=True,
        default="warn",
    )
    school_is_demo_company = fields.Boolean(
        string="TEST / DEMO Company",
        help="Marks a company that contains only synthetic test data.",
    )


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    school_prevent_self_approval = fields.Boolean(
        related="company_id.school_prevent_self_approval", readonly=False
    )
    school_require_entry_approval = fields.Boolean(
        related="company_id.school_require_entry_approval", readonly=False
    )
    school_require_vendor_bill_approval = fields.Boolean(
        related="company_id.school_require_vendor_bill_approval", readonly=False
    )
    school_require_vendor_payment_approval = fields.Boolean(
        related="company_id.school_require_vendor_payment_approval", readonly=False
    )
    school_require_student_receipt_approval = fields.Boolean(
        related="company_id.school_require_student_receipt_approval", readonly=False
    )
    school_require_student_refund_approval = fields.Boolean(
        related="company_id.school_require_student_refund_approval", readonly=False
    )
    school_require_budget_approval = fields.Boolean(
        related="company_id.school_require_budget_approval", readonly=False
    )
    school_require_asset_disposal_approval = fields.Boolean(
        related="company_id.school_require_asset_disposal_approval", readonly=False
    )
    school_prevent_duplicate_student_fees = fields.Boolean(
        related="company_id.school_prevent_duplicate_student_fees", readonly=False
    )
    school_prevent_duplicate_payment_reference = fields.Boolean(
        related="company_id.school_prevent_duplicate_payment_reference",
        readonly=False,
    )
    school_cash_negative_policy = fields.Selection(
        related="company_id.school_cash_negative_policy", readonly=False
    )

