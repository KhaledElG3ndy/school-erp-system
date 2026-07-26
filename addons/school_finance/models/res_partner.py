from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_school_student = fields.Boolean(string="Student", tracking=True)
    is_school_guardian = fields.Boolean(string="Guardian", tracking=True)
    school_student_code = fields.Char(
        string="Student Code", copy=False, index=True, tracking=True
    )
    school_guardian_code = fields.Char(
        string="Guardian Code", copy=False, index=True, tracking=True
    )
    school_guardian_ids = fields.Many2many(
        "res.partner",
        "school_student_guardian_rel",
        "student_id",
        "guardian_id",
        string="Guardians",
        domain="[('is_school_guardian', '=', True)]",
        tracking=True,
    )
    school_student_ids = fields.Many2many(
        "res.partner",
        "school_student_guardian_rel",
        "guardian_id",
        "student_id",
        string="Students",
        domain="[('is_school_student', '=', True)]",
        readonly=True,
    )
    school_financial_guardian_id = fields.Many2one(
        "res.partner",
        string="Financially Responsible Guardian",
        domain="[('is_school_guardian', '=', True)]",
        tracking=True,
    )
    school_invoice_recipient = fields.Selection(
        [("student", "Student"), ("guardian", "Financial Guardian")],
        string="Invoice Recipient",
        default="student",
        tracking=True,
    )
    school_academic_year_id = fields.Many2one(
        "school.academic.year", string="Academic Year", check_company=True
    )
    school_department_id = fields.Many2one(
        "school.department", string="Department / Cost Center", check_company=True
    )
    school_student_status = fields.Selection(
        [
            ("active", "Active"),
            ("graduated", "Graduated"),
            ("withdrawn", "Withdrawn"),
            ("suspended", "Suspended"),
        ],
        default="active",
        string="Student Status",
        tracking=True,
    )
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)
    school_invoice_count = fields.Integer(
        string="School Invoices", compute="_compute_school_finance_counts"
    )
    school_payment_count = fields.Integer(
        string="School Payments", compute="_compute_school_finance_counts"
    )

    _student_code_unique = models.Constraint(
        "UNIQUE (school_student_code)",
        "The student code must be unique.",
    )
    _guardian_code_unique = models.Constraint(
        "UNIQUE (school_guardian_code)",
        "The guardian code must be unique.",
    )

    @api.constrains(
        "is_school_student",
        "is_school_guardian",
        "school_student_code",
        "school_guardian_code",
        "school_guardian_ids",
        "school_financial_guardian_id",
        "school_invoice_recipient",
    )
    def _check_school_identity(self):
        for partner in self:
            if partner.is_school_student and not partner.school_student_code:
                raise ValidationError(_("A student code is required for every student."))
            if partner.is_school_guardian and not partner.school_guardian_code:
                raise ValidationError(_("A guardian code is required for every guardian."))
            if partner.school_financial_guardian_id:
                if not partner.school_financial_guardian_id.is_school_guardian:
                    raise ValidationError(
                        _("The financially responsible contact must be a guardian.")
                    )
                if partner.school_financial_guardian_id not in partner.school_guardian_ids:
                    raise ValidationError(
                        _("The financially responsible guardian must be linked to the student.")
                    )
            if (
                partner.is_school_student
                and partner.school_invoice_recipient == "guardian"
                and not partner.school_financial_guardian_id
            ):
                raise ValidationError(
                    _("Select a financial guardian when invoices are issued to a guardian.")
                )

    def _compute_school_finance_counts(self):
        Move = self.env["account.move"]
        Payment = self.env["account.payment"]
        for partner in self:
            student_ids = partner.ids if partner.is_school_student else partner.school_student_ids.ids
            partner.school_invoice_count = Move.search_count(
                [
                    "|",
                    ("school_student_id", "in", student_ids or [0]),
                    ("school_guardian_id", "=", partner.id),
                    ("move_type", "in", ("out_invoice", "out_refund")),
                ]
            )
            partner.school_payment_count = Payment.search_count(
                [
                    "|",
                    ("school_student_id", "in", student_ids or [0]),
                    ("school_guardian_id", "=", partner.id),
                ]
            )

    def action_open_school_invoices(self):
        self.ensure_one()
        student_ids = self.ids if self.is_school_student else self.school_student_ids.ids
        return {
            "name": _("School Invoices"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [
                "|",
                ("school_student_id", "in", student_ids or [0]),
                ("school_guardian_id", "=", self.id),
                ("move_type", "in", ("out_invoice", "out_refund")),
            ],
            "context": {"default_move_type": "out_invoice"},
        }

    def action_open_school_payments(self):
        self.ensure_one()
        student_ids = self.ids if self.is_school_student else self.school_student_ids.ids
        return {
            "name": _("School Payments"),
            "type": "ir.actions.act_window",
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": [
                "|",
                ("school_student_id", "in", student_ids or [0]),
                ("school_guardian_id", "=", self.id),
            ],
        }

