from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SchoolFeeBatch(models.Model):
    _name = "school.fee.batch"
    _description = "School Fee Batch"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        required=True,
        default=lambda self: _("New"),
        copy=False,
        readonly=True,
        tracking=True,
    )
    date = fields.Date(
        string="Invoice Date",
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    due_date = fields.Date(required=True, tracking=True)
    academic_year_id = fields.Many2one(
        "school.academic.year", required=True, check_company=True, tracking=True
    )
    term = fields.Selection(
        [
            ("annual", "Annual"),
            ("term_1", "First Term"),
            ("term_2", "Second Term"),
            ("term_3", "Third Term"),
            ("monthly", "Monthly"),
            ("other", "Other"),
        ],
        required=True,
        default="term_1",
        tracking=True,
    )
    installment_plan_id = fields.Many2one(
        "school.installment.plan", check_company=True, tracking=True
    )
    student_ids = fields.Many2many(
        "res.partner",
        "school_fee_batch_student_rel",
        "batch_id",
        "student_id",
        string="Students",
        required=True,
        domain="[('is_school_student', '=', True), ('school_student_status', '=', 'active')]",
    )
    line_ids = fields.One2many(
        "school.fee.batch.line", "batch_id", string="Fees", copy=True
    )
    invoice_ids = fields.One2many(
        "account.move", "school_fee_batch_id", string="Generated Invoices", readonly=True
    )
    invoice_count = fields.Integer(compute="_compute_invoice_count")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("reviewed", "Reviewed"),
            ("approved", "Approved"),
            ("done", "Invoices Generated"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    rejection_reason = fields.Text(copy=False, tracking=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", readonly=True, store=True
    )
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = sequence.next_by_code("school.fee.batch") or _("New")
        return super().create(vals_list)

    @api.depends("invoice_ids")
    def _compute_invoice_count(self):
        for batch in self:
            batch.invoice_count = len(batch.invoice_ids)

    @api.constrains("date", "due_date", "student_ids", "line_ids")
    def _check_batch(self):
        for batch in self:
            if batch.date and batch.due_date and batch.due_date < batch.date:
                raise ValidationError(_("The due date cannot be earlier than the invoice date."))
            if not batch.student_ids:
                raise ValidationError(_("Select at least one student."))
            if not batch.line_ids:
                raise ValidationError(_("Add at least one fee line."))

    def action_submit(self):
        if any(batch.state != "draft" for batch in self):
            raise UserError(_("Only draft batches can be submitted."))
        self.write(
            {
                "state": "submitted",
                "submitted_by_id": self.env.user.id,
                "rejection_reason": False,
            }
        )
        return True

    def action_review(self):
        if not self.env.user.has_group(
            "school_finance.group_school_finance_reviewer"
        ):
            raise AccessError(_("Only a finance reviewer can review fee batches."))
        if any(batch.state != "submitted" for batch in self):
            raise UserError(_("Only submitted batches can be reviewed."))
        self.write({"state": "reviewed", "reviewed_by_id": self.env.user.id})
        return True

    def action_approve(self):
        if not self.env.user.has_group(
            "school_finance.group_school_finance_approver"
        ):
            raise AccessError(_("Only a finance approver can approve fee batches."))
        if any(batch.state != "reviewed" for batch in self):
            raise UserError(_("Only reviewed batches can be approved."))
        if any(
            batch.company_id.school_prevent_self_approval
            and batch.create_uid == self.env.user
            for batch in self
        ):
            raise UserError(_("You cannot approve a fee batch that you created."))
        self.write({"state": "approved", "approved_by_id": self.env.user.id})
        return True

    def action_return(self):
        if not self.env.user.has_group(
            "school_finance.group_school_finance_reviewer"
        ):
            raise AccessError(_("Only a finance reviewer can return fee batches."))
        if any(not batch.rejection_reason for batch in self):
            raise UserError(_("Enter a reason before returning the batch."))
        self.write(
            {
                "state": "draft",
                "reviewed_by_id": False,
                "approved_by_id": False,
            }
        )
        return True

    def action_cancel(self):
        if any(batch.invoice_ids for batch in self):
            raise UserError(_("A batch with generated invoices cannot be cancelled."))
        self.write({"state": "cancel"})

    def action_generate_invoices(self):
        Move = self.env["account.move"]
        for batch in self:
            if batch.state != "approved":
                raise UserError(_("Approve the fee batch before generating invoices."))
            if batch.invoice_ids:
                raise UserError(_("Invoices have already been generated for this batch."))
            for student in batch.student_ids:
                guardian = student.school_financial_guardian_id
                if student.school_invoice_recipient == "guardian" and not guardian:
                    raise UserError(
                        _("Student %s has no financially responsible guardian.")
                        % student.display_name
                    )
                partner = (
                    guardian
                    if student.school_invoice_recipient == "guardian"
                    else student
                )
                invoice_lines = []
                for line in batch.line_ids:
                    analytic_distribution = False
                    department = line.department_id or line.fee_type_id.department_id
                    if department.analytic_account_id:
                        analytic_distribution = {
                            str(department.analytic_account_id.id): 100.0
                        }
                    invoice_lines.append(
                        fields.Command.create(
                            {
                                "name": line.fee_type_id.name,
                                "product_id": line.fee_type_id.product_id.id,
                                "account_id": line.fee_type_id.income_account_id.id,
                                "quantity": line.quantity,
                                "price_unit": line.unit_price,
                                "discount": line.discount,
                                "tax_ids": [fields.Command.set(line.tax_ids.ids)],
                                "analytic_distribution": analytic_distribution,
                                "school_fee_type_id": line.fee_type_id.id,
                                "school_department_id": department.id,
                                "school_is_grant": line.is_grant,
                                "school_discount_reason": line.discount_reason,
                            }
                        )
                    )
                Move.create(
                    {
                        "move_type": "out_invoice",
                        "partner_id": partner.id,
                        "invoice_date": batch.date,
                        "invoice_date_due": batch.due_date,
                        "invoice_payment_term_id": batch.installment_plan_id.payment_term_id.id,
                        "school_student_id": student.id,
                        "school_guardian_id": guardian.id,
                        "school_academic_year_id": batch.academic_year_id.id,
                        "school_term": batch.term,
                        "school_installment_plan_id": batch.installment_plan_id.id,
                        "school_fee_batch_id": batch.id,
                        "school_demo_data": batch.school_demo_data,
                        "invoice_line_ids": invoice_lines,
                    }
                )
            batch.state = "done"
        return self.action_open_invoices()

    def action_open_invoices(self):
        self.ensure_one()
        return {
            "name": _("Generated School Invoices"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.invoice_ids.ids)],
            "context": {"default_move_type": "out_invoice"},
        }


class SchoolFeeBatchLine(models.Model):
    _name = "school.fee.batch.line"
    _description = "School Fee Batch Line"
    _order = "sequence, id"
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    batch_id = fields.Many2one(
        "school.fee.batch", required=True, ondelete="cascade", index=True
    )
    fee_type_id = fields.Many2one(
        "school.fee.type", required=True, check_company=True
    )
    department_id = fields.Many2one("school.department", check_company=True)
    quantity = fields.Float(required=True, default=1.0)
    unit_price = fields.Monetary(required=True)
    discount = fields.Float(string="Discount %", default=0.0)
    is_grant = fields.Boolean(string="Grant / Scholarship")
    discount_reason = fields.Char()
    tax_ids = fields.Many2many(
        "account.tax",
        "school_fee_batch_line_tax_rel",
        "line_id",
        "tax_id",
        check_company=True,
        domain="[('type_tax_use', '=', 'sale')]",
    )
    subtotal = fields.Monetary(compute="_compute_subtotal")
    currency_id = fields.Many2one(
        related="batch_id.currency_id", readonly=True, store=True
    )
    company_id = fields.Many2one(
        related="batch_id.company_id", readonly=True, store=True
    )

    @api.onchange("fee_type_id")
    def _onchange_fee_type_id(self):
        if self.fee_type_id:
            self.unit_price = self.fee_type_id.default_amount
            self.department_id = self.fee_type_id.department_id
            self.tax_ids = self.fee_type_id.tax_ids

    @api.depends("quantity", "unit_price", "discount")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price * (1 - line.discount / 100)

    @api.constrains("quantity", "unit_price", "discount", "is_grant", "discount_reason")
    def _check_values(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Fee quantity must be greater than zero."))
            if line.unit_price < 0:
                raise ValidationError(_("Fee unit price cannot be negative."))
            if not 0 <= line.discount <= 100:
                raise ValidationError(_("Discount must be between 0 and 100 percent."))
            if (line.discount or line.is_grant) and not line.discount_reason:
                raise ValidationError(_("A reason is required for every discount or grant."))
