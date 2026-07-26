from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _name = "account.move"
    _inherit = ["account.move", "school.finance.approval.mixin"]

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
    school_academic_year_id = fields.Many2one(
        "school.academic.year",
        string="Academic Year",
        check_company=True,
        tracking=True,
        index=True,
    )
    school_term = fields.Selection(
        [
            ("annual", "Annual"),
            ("term_1", "First Term"),
            ("term_2", "Second Term"),
            ("term_3", "Third Term"),
            ("monthly", "Monthly"),
            ("other", "Other"),
        ],
        string="Academic Period",
        tracking=True,
        index=True,
    )
    school_installment_plan_id = fields.Many2one(
        "school.installment.plan",
        string="Installment Plan",
        check_company=True,
        tracking=True,
    )
    school_fee_batch_id = fields.Many2one(
        "school.fee.batch", string="Fee Batch", readonly=True, copy=False
    )
    school_refund_reason = fields.Text(string="Refund Reason", copy=False, tracking=True)
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)
    school_installment_line_ids = fields.One2many(
        "account.move.line",
        "move_id",
        string="Installments",
        domain=[
            ("account_id.account_type", "=", "asset_receivable"),
            ("display_type", "not in", ("line_section", "line_subsection", "line_note")),
        ],
        readonly=True,
    )
    school_is_fee_invoice = fields.Boolean(
        string="School Fee Invoice",
        compute="_compute_school_is_fee_invoice",
        store=True,
    )
    school_amount_in_process = fields.Monetary(
        string="Receipts Awaiting Bank Matching",
        compute="_compute_school_collection_amounts",
        currency_field="currency_id",
    )
    school_collection_residual = fields.Monetary(
        string="School Collection Balance",
        compute="_compute_school_collection_amounts",
        currency_field="currency_id",
        help="Accounting residual less linked payments that are still awaiting bank/cash matching in Odoo 19.",
    )

    @api.depends("school_student_id", "move_type")
    def _compute_school_is_fee_invoice(self):
        for move in self:
            move.school_is_fee_invoice = bool(
                move.school_student_id
                and move.move_type in ("out_invoice", "out_refund")
            )

    @api.depends(
        "amount_residual",
        "matched_payment_ids",
        "matched_payment_ids.amount",
        "matched_payment_ids.state",
        "matched_payment_ids.move_id",
    )
    def _compute_school_collection_amounts(self):
        for move in self:
            pending = move.matched_payment_ids.filtered(
                lambda payment: not payment.move_id
                and payment.state in ("in_process", "paid")
            )
            amount = sum(
                payment.currency_id._convert(
                    payment.amount,
                    move.currency_id,
                    move.company_id,
                    payment.date,
                )
                for payment in pending
            )
            move.school_amount_in_process = amount
            move.school_collection_residual = max(move.amount_residual - amount, 0.0)

    @api.depends(
        "company_id",
        "move_type",
        "school_student_id",
        "origin_payment_id",
        "company_id.school_require_entry_approval",
        "company_id.school_require_vendor_bill_approval",
        "company_id.school_require_student_refund_approval",
    )
    def _compute_school_approval_required(self):
        return super()._compute_school_approval_required()

    def _school_requires_approval(self):
        self.ensure_one()
        if self.origin_payment_id:
            return False
        if self.move_type == "entry":
            return self.company_id.school_require_entry_approval
        if self.move_type in ("in_invoice", "in_refund"):
            return self.company_id.school_require_vendor_bill_approval
        if self.move_type == "out_refund" and self.school_student_id:
            return self.company_id.school_require_student_refund_approval
        return False

    @api.onchange("school_student_id")
    def _onchange_school_student_id(self):
        for move in self:
            if not move.school_student_id:
                continue
            student = move.school_student_id
            move.school_guardian_id = student.school_financial_guardian_id
            move.school_academic_year_id = student.school_academic_year_id
            if student.school_invoice_recipient == "guardian":
                move.partner_id = student.school_financial_guardian_id
            else:
                move.partner_id = student

    @api.onchange("school_installment_plan_id")
    def _onchange_school_installment_plan_id(self):
        for move in self:
            move.invoice_payment_term_id = (
                move.school_installment_plan_id.payment_term_id
            )

    @api.constrains(
        "school_student_id",
        "school_guardian_id",
        "partner_id",
        "move_type",
    )
    def _check_school_parties(self):
        for move in self:
            if not move.school_student_id:
                continue
            if not move.school_student_id.is_school_student:
                raise ValidationError(_("The selected contact is not marked as a student."))
            if move.school_guardian_id and not move.school_guardian_id.is_school_guardian:
                raise ValidationError(_("The selected guardian is not marked as a guardian."))
            student = move.school_student_id
            expected_partner = (
                student.school_financial_guardian_id
                if student.school_invoice_recipient == "guardian"
                else student
            )
            if (
                move.move_type in ("out_invoice", "out_refund")
                and expected_partner
                and move.partner_id != expected_partner
            ):
                raise ValidationError(
                    _(
                        "The invoice customer must match the student's configured invoice recipient."
                    )
                )

    def _check_duplicate_school_fees(self):
        Line = self.env["account.move.line"]
        for move in self.filtered(
            lambda item: item.move_type == "out_invoice"
            and item.state != "cancel"
            and item.school_student_id
            and item.company_id.school_prevent_duplicate_student_fees
        ):
            if not move.school_academic_year_id or not move.school_term:
                raise ValidationError(
                    _("Academic year and academic period are required on school fee invoices.")
                )
            fee_lines = move.invoice_line_ids.filtered("school_fee_type_id")
            for line in fee_lines:
                duplicate = Line.search(
                    [
                        ("id", "!=", line.id),
                        ("move_id", "!=", move.id),
                        ("move_id.state", "!=", "cancel"),
                        ("move_id.move_type", "=", "out_invoice"),
                        ("move_id.company_id", "=", move.company_id.id),
                        ("move_id.school_student_id", "=", move.school_student_id.id),
                        (
                            "move_id.school_academic_year_id",
                            "=",
                            move.school_academic_year_id.id,
                        ),
                        ("move_id.school_term", "=", move.school_term),
                        ("school_fee_type_id", "=", line.school_fee_type_id.id),
                    ],
                    limit=1,
                )
                if duplicate:
                    raise ValidationError(
                        _(
                            "Fee %(fee)s is already invoiced to student %(student)s for the same academic period.",
                            fee=line.school_fee_type_id.display_name,
                            student=move.school_student_id.display_name,
                        )
                    )

    @api.constrains(
        "school_student_id",
        "school_academic_year_id",
        "school_term",
        "invoice_line_ids",
        "state",
    )
    def _constraint_duplicate_school_fees(self):
        self._check_duplicate_school_fees()

    def _post(self, soft=True):
        to_post_now = self.filtered(
            lambda move: not soft
            or not move.date
            or move.date <= fields.Date.context_today(move)
        )
        to_post_now._school_check_approved()
        missing_reason = to_post_now.filtered(
            lambda move: move.move_type == "out_refund"
            and move.school_student_id
            and not move.school_refund_reason
        )
        if missing_reason:
            raise UserError(_("A refund reason is required for every student credit note."))
        self._check_duplicate_school_fees()
        return super()._post(soft=soft)

    def action_open_school_installments(self):
        self.ensure_one()
        return {
            "name": _("Student Installments"),
            "type": "ir.actions.act_window",
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": [
                ("move_id", "=", self.id),
                ("account_id.account_type", "=", "asset_receivable"),
            ],
            "context": {"create": False},
        }


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    school_fee_type_id = fields.Many2one(
        "school.fee.type", string="Fee Type", check_company=True, index=True
    )
    school_department_id = fields.Many2one(
        "school.department", string="Department / Cost Center", check_company=True
    )
    school_is_grant = fields.Boolean(string="Grant / Scholarship")
    school_discount_reason = fields.Char(string="Discount / Grant Reason")

    @api.onchange("school_fee_type_id")
    def _onchange_school_fee_type_id(self):
        for line in self:
            fee = line.school_fee_type_id
            if not fee:
                continue
            line.name = fee.name
            line.product_id = fee.product_id
            line.account_id = fee.income_account_id
            line.price_unit = fee.default_amount
            line.tax_ids = fee.tax_ids
            line.school_department_id = fee.department_id
            if fee.department_id.analytic_account_id:
                line.analytic_distribution = {
                    str(fee.department_id.analytic_account_id.id): 100.0
                }

    @api.constrains(
        "school_fee_type_id",
        "school_department_id",
        "school_is_grant",
        "school_discount_reason",
        "discount",
    )
    def _check_school_fee_line(self):
        for line in self:
            if (line.discount or line.school_is_grant) and not line.school_discount_reason:
                raise ValidationError(
                    _("A reason is required for every school fee discount or grant.")
                )
        self.move_id._check_duplicate_school_fees()
