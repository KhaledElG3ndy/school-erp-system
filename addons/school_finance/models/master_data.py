from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolAcademicYear(models.Model):
    _name = "school.academic.year"
    _description = "School Academic Year"
    _order = "date_from desc, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    date_from = fields.Date(string="Start Date", required=True)
    date_to = fields.Date(string="End Date", required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("open", "Open"), ("closed", "Closed")],
        required=True,
        default="draft",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)

    _code_company_unique = models.Constraint(
        "UNIQUE (code, company_id)",
        "The academic year code must be unique per company.",
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for record in self:
            if record.date_from and record.date_to and record.date_from > record.date_to:
                raise ValidationError(_("The academic year end date must follow its start date."))

    def action_open(self):
        self.write({"state": "open"})

    def action_close(self):
        self.write({"state": "closed"})

    def action_draft(self):
        self.write({"state": "draft"})


class SchoolDepartment(models.Model):
    _name = "school.department"
    _description = "School Department / Cost Center"
    _order = "code, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    analytic_account_id = fields.Many2one(
        "account.analytic.account",
        string="Analytic Cost Center",
        check_company=True,
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)

    _code_company_unique = models.Constraint(
        "UNIQUE (code, company_id)",
        "The department code must be unique per company.",
    )


class SchoolFeeType(models.Model):
    _name = "school.fee.type"
    _description = "School Fee Type"
    _order = "code, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    frequency = fields.Selection(
        [
            ("one_time", "One Time"),
            ("monthly", "Monthly"),
            ("term", "Academic Term"),
            ("annual", "Annual"),
        ],
        required=True,
        default="term",
    )
    default_amount = fields.Monetary(required=True, default=0.0)
    currency_id = fields.Many2one(
        related="company_id.currency_id", readonly=True, store=True
    )
    product_id = fields.Many2one("product.product", check_company=True)
    income_account_id = fields.Many2one(
        "account.account",
        required=True,
        check_company=True,
        domain="[('account_type', 'in', ('income', 'income_other'))]",
    )
    tax_ids = fields.Many2many(
        "account.tax",
        "school_fee_type_tax_rel",
        "fee_type_id",
        "tax_id",
        string="Default Taxes",
        check_company=True,
        domain="[('type_tax_use', '=', 'sale')]",
    )
    department_id = fields.Many2one(
        "school.department", string="Default Department", check_company=True
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)

    _code_company_unique = models.Constraint(
        "UNIQUE (code, company_id)",
        "The fee type code must be unique per company.",
    )

    @api.constrains("default_amount")
    def _check_amount(self):
        if any(record.default_amount < 0 for record in self):
            raise ValidationError(_("The default fee amount cannot be negative."))


class SchoolInstallmentPlan(models.Model):
    _name = "school.installment.plan"
    _description = "School Installment Plan"
    _order = "code, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    payment_term_id = fields.Many2one(
        "account.payment.term",
        string="Odoo Payment Term",
        required=True,
        check_company=True,
        help="Installment due dates and percentages are maintained in the standard Odoo payment term.",
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    active = fields.Boolean(default=True)
    school_demo_data = fields.Boolean(string="TEST / DEMO Data", default=False)

    _code_company_unique = models.Constraint(
        "UNIQUE (code, company_id)",
        "The installment plan code must be unique per company.",
    )
