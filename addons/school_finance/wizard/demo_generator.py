import re
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError


class SchoolFinanceDemoGenerator(models.TransientModel):
    _name = "school.finance.demo.generator"
    _description = "Generate Synthetic School Finance Demo Data"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    confirm_demo = fields.Boolean(
        string="I confirm this is a TEST / DEMO database"
    )
    result_message = fields.Text(readonly=True)

    def _check_safe_database(self):
        self.ensure_one()
        safe_name = bool(
            re.search(
                r"(test|demo|staging|stage|clone|codex)",
                self.env.cr.dbname,
                flags=re.IGNORECASE,
            )
        )
        if not self.confirm_demo:
            raise UserError(_("Confirm that this is a TEST / DEMO database."))
        if not safe_name and not self.company_id.school_is_demo_company:
            raise UserError(
                _(
                    "Demo generation is blocked on this database. Use a clone/test database or mark a dedicated company as TEST / DEMO."
                )
            )

    def action_generate(self):
        self._check_safe_database()
        company = self.company_id
        existing = self.env["res.partner"].search_count(
            [
                ("school_demo_data", "=", True),
                ("company_id", "in", (False, company.id)),
            ],
            limit=1,
        )
        if existing:
            raise UserError(_("Synthetic school demo data already exists."))

        income = self.env["account.account"].search(
            [
                ("company_ids", "in", company.id),
                ("account_type", "in", ("income", "income_other")),
            ],
            limit=1,
        )
        if not income:
            raise UserError(
                _("Configure a chart of accounts before generating school demo data.")
            )

        today = fields.Date.context_today(self)
        year = self.env["school.academic.year"].create(
            {
                "name": "[TEST] Academic Year",
                "code": "TEST-AY-%s" % today.year,
                "date_from": today.replace(month=1, day=1),
                "date_to": today.replace(month=12, day=31),
                "state": "open",
                "company_id": company.id,
                "school_demo_data": True,
            }
        )
        plan = self.env["account.analytic.plan"].search([], limit=1)
        if not plan:
            raise UserError(
                _("Configure an analytic plan before generating school demo data.")
            )
        analytic = self.env["account.analytic.account"].create(
            {
                "name": "[TEST] Primary School Cost Center",
                "plan_id": plan.id,
                "company_id": company.id,
            }
        )
        department = self.env["school.department"].create(
            {
                "name": "[TEST] Primary School",
                "code": "TEST-PRIMARY",
                "analytic_account_id": analytic.id,
                "company_id": company.id,
                "school_demo_data": True,
            }
        )
        guardian = self.env["res.partner"].create(
            {
                "name": "[TEST] Guardian 001",
                "is_school_guardian": True,
                "school_guardian_code": "TEST-G-001",
                "email": "guardian001@example.invalid",
                "phone": "+966500000001",
                "company_id": company.id,
                "school_demo_data": True,
            }
        )
        students = self.env["res.partner"]
        for number, label in enumerate(("Paid", "Partial", "Overdue"), start=1):
            students |= self.env["res.partner"].create(
                {
                    "name": "[TEST] Student %s" % label,
                    "is_school_student": True,
                    "school_student_code": "TEST-S-%03d" % number,
                    "school_guardian_ids": [fields.Command.link(guardian.id)],
                    "school_financial_guardian_id": guardian.id,
                    "school_invoice_recipient": "guardian",
                    "school_academic_year_id": year.id,
                    "school_department_id": department.id,
                    "company_id": company.id,
                    "school_demo_data": True,
                }
            )
        fee_type = self.env["school.fee.type"].create(
            {
                "name": "[TEST] Tuition Fee",
                "code": "TEST-TUITION",
                "frequency": "term",
                "default_amount": 1000.0,
                "income_account_id": income.id,
                "department_id": department.id,
                "company_id": company.id,
                "school_demo_data": True,
            }
        )
        payment_term = self.env["account.payment.term"].create(
            {
                "name": "[TEST] Two Installments",
                "company_id": company.id,
                "line_ids": [
                    fields.Command.clear(),
                    fields.Command.create(
                        {"value": "percent", "value_amount": 50.0, "nb_days": 0}
                    ),
                    fields.Command.create(
                        {"value": "percent", "value_amount": 50.0, "nb_days": 30}
                    ),
                ],
            }
        )
        installment = self.env["school.installment.plan"].create(
            {
                "name": "[TEST] Two Installments",
                "code": "TEST-2-INST",
                "payment_term_id": payment_term.id,
                "company_id": company.id,
                "school_demo_data": True,
            }
        )
        batch = self.env["school.fee.batch"].create(
            {
                "date": today - timedelta(days=45),
                "due_date": today - timedelta(days=15),
                "academic_year_id": year.id,
                "term": "term_1",
                "installment_plan_id": installment.id,
                "student_ids": [fields.Command.set(students.ids)],
                "line_ids": [
                    fields.Command.create(
                        {
                            "fee_type_id": fee_type.id,
                            "department_id": department.id,
                            "quantity": 1.0,
                            "unit_price": 1000.0,
                        }
                    )
                ],
                "company_id": company.id,
                "school_demo_data": True,
                "state": "approved",
                "submitted_by_id": self.env.user.id,
                "reviewed_by_id": self.env.user.id,
                "approved_by_id": self.env.user.id,
            }
        )
        batch.action_generate_invoices()
        self.result_message = _(
            "Created synthetic master data and %(count)s draft invoices. All names are prefixed [TEST] and records are tagged as TEST / DEMO.",
            count=len(batch.invoice_ids),
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
