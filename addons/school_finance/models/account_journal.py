from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = "account.journal"

    school_cashier_id = fields.Many2one(
        "res.users",
        string="Responsible Cashier",
        tracking=True,
        domain="[('share', '=', False)]",
    )
    school_authorized_user_ids = fields.Many2many(
        "res.users",
        "school_journal_authorized_user_rel",
        "journal_id",
        "user_id",
        string="Authorized Users",
        help="Leave empty to use the standard Odoo accounting access rules.",
    )
    school_disbursement_approval_limit = fields.Monetary(
        string="Disbursement Approval Threshold",
        currency_field="currency_id",
        help="Outbound payments at or above this amount require the school finance workflow.",
    )
