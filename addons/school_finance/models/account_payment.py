from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "school.finance.approval.mixin"]

    school_student_id = fields.Many2one(
        "res.partner",
        string="Student",
        domain="[('is_school_student', '=', True)]",
        tracking=True,
        index=True,
    )
    school_guardian_id = fields.Many2one(
        "res.partner",
        string="Guardian",
        domain="[('is_school_guardian', '=', True)]",
        tracking=True,
        index=True,
    )
    school_payment_reference = fields.Char(
        string="School Payment Reference", copy=False, tracking=True, index=True
    )
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)

    @api.depends(
        "company_id",
        "payment_type",
        "partner_type",
        "journal_id",
        "amount",
        "company_id.school_require_vendor_payment_approval",
        "company_id.school_require_student_receipt_approval",
    )
    def _compute_school_approval_required(self):
        return super()._compute_school_approval_required()

    def _school_requires_approval(self):
        self.ensure_one()
        if (
            self.payment_type == "outbound"
            and self.partner_type == "supplier"
            and self.company_id.school_require_vendor_payment_approval
        ):
            return True
        if (
            self.payment_type == "inbound"
            and self.school_student_id
            and self.company_id.school_require_student_receipt_approval
        ):
            return True
        if (
            self.payment_type == "outbound"
            and self.journal_id.school_disbursement_approval_limit
            and self.amount >= self.journal_id.school_disbursement_approval_limit
        ):
            return True
        return False

    @api.onchange("school_student_id")
    def _onchange_school_student_id(self):
        for payment in self:
            if not payment.school_student_id:
                continue
            student = payment.school_student_id
            payment.school_guardian_id = student.school_financial_guardian_id
            payment.partner_id = (
                student.school_financial_guardian_id
                if student.school_invoice_recipient == "guardian"
                else student
            )
            payment.partner_type = "customer"

    def _school_check_duplicate_reference(self):
        for payment in self.filtered(
            lambda item: item.school_payment_reference
            and item.company_id.school_prevent_duplicate_payment_reference
            and item.state not in ("canceled", "rejected")
        ):
            duplicate = self.search(
                [
                    ("id", "!=", payment.id),
                    ("company_id", "=", payment.company_id.id),
                    ("journal_id", "=", payment.journal_id.id),
                    ("school_payment_reference", "=", payment.school_payment_reference),
                    ("state", "not in", ("canceled", "rejected")),
                ],
                limit=1,
            )
            if duplicate:
                raise UserError(
                    _("This school payment reference has already been used in this journal.")
                )

    def _school_check_journal_access(self):
        for payment in self:
            users = payment.journal_id.school_authorized_user_ids
            if (
                users
                and self.env.user not in users
                and not self.env.user.has_group(
                    "school_finance.group_school_finance_manager"
                )
            ):
                raise AccessError(_("You are not authorized to use this journal."))

    def _school_check_negative_cash(self):
        for payment in self.filtered(
            lambda item: item.payment_type == "outbound"
            and item.journal_id.type == "cash"
            and item.company_id.school_cash_negative_policy != "allow"
        ):
            accounts = (
                payment.journal_id.default_account_id
                | payment.outstanding_account_id
            ).filtered(lambda account: account.account_type == "asset_cash")
            if not accounts:
                continue
            grouped = self.env["account.move.line"]._read_group(
                [
                    ("company_id", "=", payment.company_id.id),
                    ("parent_state", "=", "posted"),
                    ("account_id", "in", accounts.ids),
                    ("date", "<=", payment.date),
                ],
                aggregates=["balance:sum"],
            )
            balance = grouped[0][0] if grouped else 0.0
            if payment.company_id.currency_id.compare_amounts(balance, payment.amount) < 0:
                if payment.company_id.school_cash_negative_policy == "block":
                    raise UserError(
                        _("This payment would make the configured cash balance negative.")
                    )
                payment.message_post(
                    body=_(
                        "Warning: this payment may make the configured cash balance negative."
                    )
                )

    def action_post(self):
        self._school_check_approved()
        self._school_check_duplicate_reference()
        self._school_check_journal_access()
        self._school_check_negative_cash()
        return super().action_post()
