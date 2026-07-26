from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("school_finance", "post_install", "-at_install")
class TestSchoolFinance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write(
            {
                "school_prevent_self_approval": False,
                "school_prevent_duplicate_student_fees": True,
                "school_prevent_duplicate_payment_reference": True,
            }
        )
        cls.income_account = cls.env["account.account"].search(
            [
                ("company_ids", "in", cls.company.id),
                ("account_type", "in", ("income", "income_other")),
            ],
            limit=1,
        )
        cls.expense_account = cls.env["account.account"].search(
            [
                ("company_ids", "in", cls.company.id),
                (
                    "account_type",
                    "in",
                    ("expense", "expense_direct_cost", "expense_depreciation"),
                ),
            ],
            limit=1,
        )
        cls.receivable_account = cls.env["account.account"].search(
            [
                ("company_ids", "in", cls.company.id),
                ("account_type", "=", "asset_receivable"),
            ],
            limit=1,
        )
        cls.general_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.company.id), ("type", "=", "general")],
            limit=1,
        )
        cls.bank_journal = cls.env["account.journal"].search(
            [
                ("company_id", "=", cls.company.id),
                ("type", "in", ("bank", "cash")),
            ],
            limit=1,
        )
        cls.analytic_plan = cls.env["account.analytic.plan"].search([], limit=1)
        cls.analytic_account = cls.env["account.analytic.account"].create(
            {
                "name": "TEST Automated Cost Center",
                "plan_id": cls.analytic_plan.id,
                "company_id": cls.company.id,
            }
        )
        cls.department = cls.env["school.department"].create(
            {
                "name": "TEST Automated Department",
                "code": "TEST-DEPT-AUTOMATED",
                "analytic_account_id": cls.analytic_account.id,
                "company_id": cls.company.id,
            }
        )
        cls.academic_year = cls.env["school.academic.year"].create(
            {
                "name": "TEST Academic Year",
                "code": "TEST-AY-AUTOMATED",
                "date_from": fields.Date.today().replace(month=1, day=1),
                "date_to": fields.Date.today().replace(month=12, day=31),
                "company_id": cls.company.id,
            }
        )
        cls.guardian = cls.env["res.partner"].create(
            {
                "name": "TEST Guardian Automated",
                "is_school_guardian": True,
                "school_guardian_code": "TEST-G-AUTOMATED",
                "company_id": cls.company.id,
            }
        )
        cls.student = cls.env["res.partner"].create(
            {
                "name": "TEST Student Automated",
                "is_school_student": True,
                "school_student_code": "TEST-S-AUTOMATED",
                "school_guardian_ids": [fields.Command.link(cls.guardian.id)],
                "school_financial_guardian_id": cls.guardian.id,
                "school_invoice_recipient": "guardian",
                "school_academic_year_id": cls.academic_year.id,
                "company_id": cls.company.id,
            }
        )
        cls.fee_type = cls.env["school.fee.type"].create(
            {
                "name": "TEST Tuition Automated",
                "code": "TEST-FEE-AUTOMATED",
                "default_amount": 1000.0,
                "income_account_id": cls.income_account.id,
                "company_id": cls.company.id,
            }
        )

    def _create_fee_invoice(self, term="term_1", amount=1000.0):
        return self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.guardian.id,
                "invoice_date": fields.Date.today(),
                "school_student_id": self.student.id,
                "school_guardian_id": self.guardian.id,
                "school_academic_year_id": self.academic_year.id,
                "school_term": term,
                "invoice_line_ids": [
                    fields.Command.create(
                        {
                            "name": self.fee_type.name,
                            "account_id": self.income_account.id,
                            "quantity": 1.0,
                            "price_unit": amount,
                            "school_fee_type_id": self.fee_type.id,
                            "school_department_id": self.department.id,
                            "analytic_distribution": {
                                str(self.analytic_account.id): 100.0
                            },
                        }
                    )
                ],
            }
        )

    def _create_balanced_entry(self, amount=100.0, analytic=False):
        debit_values = {
            "name": "TEST Debit",
            "account_id": self.expense_account.id,
            "debit": amount,
        }
        credit_values = {
            "name": "TEST Credit",
            "account_id": self.income_account.id,
            "credit": amount,
        }
        if analytic:
            distribution = {str(self.analytic_account.id): 100.0}
            debit_values["analytic_distribution"] = distribution
            credit_values["analytic_distribution"] = distribution
        return self.env["account.move"].create(
            {
                "move_type": "entry",
                "journal_id": self.general_journal.id,
                "date": fields.Date.today(),
                "line_ids": [
                    fields.Command.create(debit_values),
                    fields.Command.create(credit_values),
                ],
            }
        )

    def test_student_guardian_and_duplicate_code_controls(self):
        self.assertIn(self.guardian, self.student.school_guardian_ids)
        self.assertIn(self.student, self.guardian.school_student_ids)
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.env["res.partner"].create(
                {
                    "name": "TEST Duplicate Student",
                    "is_school_student": True,
                    "school_student_code": self.student.school_student_code,
                }
            )

    def test_fee_batch_generates_linked_invoice(self):
        batch = self.env["school.fee.batch"].create(
            {
                "date": fields.Date.today(),
                "due_date": fields.Date.today() + timedelta(days=30),
                "academic_year_id": self.academic_year.id,
                "term": "term_1",
                "student_ids": [fields.Command.link(self.student.id)],
                "line_ids": [
                    fields.Command.create(
                        {
                            "fee_type_id": self.fee_type.id,
                            "quantity": 1.0,
                            "unit_price": 1000.0,
                        }
                    )
                ],
                "state": "approved",
            }
        )
        batch.action_generate_invoices()
        self.assertEqual(batch.state, "done")
        self.assertEqual(len(batch.invoice_ids), 1)
        invoice = batch.invoice_ids
        self.assertEqual(invoice.partner_id, self.guardian)
        self.assertEqual(invoice.school_student_id, self.student)
        self.assertEqual(invoice.invoice_line_ids.school_fee_type_id, self.fee_type)

    def test_duplicate_fee_is_blocked(self):
        self._create_fee_invoice()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._create_fee_invoice()

    def test_discount_or_grant_requires_a_reason(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env["school.fee.batch"].create(
                {
                    "date": fields.Date.today(),
                    "due_date": fields.Date.today() + timedelta(days=30),
                    "academic_year_id": self.academic_year.id,
                    "term": "term_1",
                    "student_ids": [fields.Command.link(self.student.id)],
                    "line_ids": [
                        fields.Command.create(
                            {
                                "fee_type_id": self.fee_type.id,
                                "quantity": 1.0,
                                "unit_price": 1000.0,
                                "discount": 10.0,
                            }
                        )
                    ],
                }
            )

    def test_entry_approval_blocks_posting_until_approved(self):
        self.company.school_require_entry_approval = True
        move = self._create_balanced_entry()
        self.assertTrue(move.school_approval_required)
        with self.assertRaises(UserError):
            move.action_post()
        move.action_school_submit()
        move.action_school_review()
        move.action_school_approve()
        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertEqual(move.school_approved_by_id, self.env.user)

    def test_student_refund_requires_reason(self):
        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.guardian.id,
                "invoice_date": fields.Date.today(),
                "school_student_id": self.student.id,
                "school_guardian_id": self.guardian.id,
                "school_academic_year_id": self.academic_year.id,
                "school_term": "term_1",
                "invoice_line_ids": [
                    fields.Command.create(
                        {
                            "name": "TEST Refund",
                            "account_id": self.income_account.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                        }
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            refund.action_post()
        refund.school_refund_reason = "TEST partial refund"
        refund.action_post()
        self.assertEqual(refund.state, "posted")

    def test_payment_register_propagates_student_and_partial_balance(self):
        invoice = self._create_fee_invoice(term="term_2")
        invoice.action_post()
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "amount": 400.0,
                    "payment_date": fields.Date.today(),
                    "journal_id": self.bank_journal.id,
                    "school_payment_reference": "TEST-PAY-001",
                }
            )
        )
        payments = wizard._create_payments()
        self.assertEqual(payments.school_student_id, self.student)
        self.assertEqual(payments.school_guardian_id, self.guardian)
        self.assertEqual(payments.school_payment_reference, "TEST-PAY-001")
        self.assertIn(invoice.payment_state, ("partial", "in_payment"))
        self.assertEqual(invoice.amount_residual, 1000.0)
        self.assertEqual(invoice.school_amount_in_process, 400.0)
        self.assertEqual(invoice.school_collection_residual, 600.0)

    def test_payment_register_keeps_approval_payment_in_draft(self):
        self.company.school_require_student_receipt_approval = True
        invoice = self._create_fee_invoice(term="other")
        invoice.action_post()
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "amount": 300.0,
                    "payment_date": fields.Date.today(),
                    "journal_id": self.bank_journal.id,
                    "school_payment_reference": "TEST-APPROVAL-001",
                }
            )
        )
        payment = wizard._create_payments()
        self.assertEqual(payment.state, "draft")
        self.assertEqual(payment.school_approval_state, "submitted")
        self.assertIn(payment, invoice.matched_payment_ids)
        self.assertEqual(invoice.school_collection_residual, 1000.0)
        payment.action_school_review()
        payment.action_school_approve()
        payment.action_post()
        self.assertIn(payment.state, ("in_process", "paid"))
        self.assertEqual(invoice.school_collection_residual, 700.0)

    def test_duplicate_school_payment_reference_is_blocked(self):
        first_invoice = self._create_fee_invoice(term="term_1")
        second_invoice = self._create_fee_invoice(term="term_2")
        (first_invoice | second_invoice).action_post()
        for invoice in (first_invoice, second_invoice):
            wizard = (
                self.env["account.payment.register"]
                .with_context(active_model="account.move", active_ids=invoice.ids)
                .create(
                    {
                        "amount": 100.0,
                        "payment_date": fields.Date.today(),
                        "journal_id": self.bank_journal.id,
                        "school_payment_reference": "TEST-DUPLICATE-REFERENCE",
                    }
                )
            )
            if invoice == first_invoice:
                wizard._create_payments()
            else:
                with self.assertRaises(UserError), self.env.cr.savepoint():
                    wizard._create_payments()

    def test_budget_actual_uses_posted_entries_only(self):
        position = self.env["account.budget.post"].create(
            {
                "name": "TEST Income Position",
                "account_ids": [fields.Command.link(self.income_account.id)],
                "company_id": self.company.id,
            }
        )
        budget = self.env["crossovered.budget"].create(
            {
                "name": "TEST Budget",
                "date_from": fields.Date.today().replace(month=1, day=1),
                "date_to": fields.Date.today().replace(month=12, day=31),
                "company_id": self.company.id,
                "crossovered_budget_line": [
                    fields.Command.create(
                        {
                            "general_budget_id": position.id,
                            "date_from": fields.Date.today().replace(month=1, day=1),
                            "date_to": fields.Date.today().replace(month=12, day=31),
                            "planned_amount": 1000.0,
                            "analytic_account_id": self.analytic_account.id,
                        }
                    )
                ],
            }
        )
        line = budget.crossovered_budget_line
        move = self._create_balanced_entry(250.0, analytic=True)
        self.assertEqual(line.practical_amount, 0.0)
        move.action_post()
        line.invalidate_recordset(["practical_amount"])
        self.assertEqual(line.practical_amount, 250.0)

    def test_budget_approval_blocks_validation(self):
        self.company.school_require_budget_approval = True
        position = self.env["account.budget.post"].create(
            {
                "name": "TEST Approval Position",
                "account_ids": [fields.Command.link(self.expense_account.id)],
                "company_id": self.company.id,
            }
        )
        budget = self.env["crossovered.budget"].create(
            {
                "name": "TEST Approval Budget",
                "date_from": fields.Date.today().replace(month=1, day=1),
                "date_to": fields.Date.today().replace(month=12, day=31),
                "company_id": self.company.id,
                "crossovered_budget_line": [
                    fields.Command.create(
                        {
                            "general_budget_id": position.id,
                            "date_from": fields.Date.today().replace(month=1, day=1),
                            "date_to": fields.Date.today().replace(month=12, day=31),
                            "planned_amount": -500.0,
                        }
                    )
                ],
            }
        )
        with self.assertRaises(UserError):
            budget.action_budget_validate()
        budget.action_school_submit()
        budget.action_school_review()
        budget.action_school_approve()
        budget.action_budget_validate()
        self.assertEqual(budget.state, "validate")

    def test_asset_disposal_requires_metadata_and_approval(self):
        fixed_asset_account = self.env["account.account"].search(
            [
                ("company_ids", "in", self.company.id),
                ("account_type", "=", "asset_fixed"),
            ],
            limit=1,
        )
        category = self.env["account.asset.category"].create(
            {
                "name": "TEST Equipment Category",
                "account_asset_id": fixed_asset_account.id,
                "account_depreciation_id": fixed_asset_account.id,
                "account_depreciation_expense_id": self.expense_account.id,
                "journal_id": self.general_journal.id,
                "company_id": self.company.id,
                "method_number": 12,
                "method_period": 1,
            }
        )
        asset = self.env["account.asset.asset"].create(
            {
                "name": "TEST Classroom Equipment",
                "code": "TEST-ASSET-001",
                "value": 1200.0,
                "category_id": category.id,
                "date": fields.Date.today(),
                "company_id": self.company.id,
                "method_number": 12,
                "method_period": 1,
                "school_disposal_type": "scrap",
            }
        )
        asset.validate()
        self.assertEqual(len(asset.depreciation_line_ids), 12)
        with self.assertRaises(UserError):
            asset.set_to_close()
        self.company.school_require_asset_disposal_approval = True
        asset.school_disposal_reason = "TEST damaged beyond repair"
        self.assertTrue(asset.school_approval_required)
        with self.assertRaises(UserError):
            asset.set_to_close()

    def test_dashboard_reads_posted_school_data(self):
        invoice = self._create_fee_invoice(term="term_3", amount=750.0)
        invoice.action_post()
        dashboard = self.env["school.finance.dashboard"].create(
            {
                "date_from": fields.Date.today().replace(month=1, day=1),
                "date_to": fields.Date.today(),
                "company_id": self.company.id,
                "department_id": self.department.id,
            }
        )
        self.assertEqual(dashboard.unpaid_student_invoice_count, 1)
        self.assertEqual(dashboard.unpaid_student_invoice_amount, 750.0)
        self.assertEqual(dashboard.total_revenue, 750.0)
        self.assertIsNotNone(dashboard.bank_balance)
        self.assertIsNotNone(dashboard.cash_box_balance)
        self.assertTrue(dashboard.period_line_ids)

    def test_sa_localization_arabic_and_correct_lock_date_mapping(self):
        self.assertEqual(
            self.env["ir.module.module"].search([("name", "=", "l10n_sa")]).state,
            "installed",
        )
        arabic_env = self.env(context=dict(self.env.context, lang="ar_001"))
        english_env = self.env(context=dict(self.env.context, lang="en_US"))
        self.assertFalse(
            self.env.ref("school_finance.menu_school_finance_root").active
        )
        self.assertEqual(
            self.env.ref("school_finance.menu_school_finance_dashboard").parent_id,
            self.env.ref("account.menu_finance"),
        )
        self.assertEqual(
            self.env.ref("school_finance.menu_school_finance_students_root").parent_id,
            self.env.ref("account.menu_finance_receivables"),
        )
        self.assertEqual(
            self.env.ref("school_finance.menu_school_finance_fees_root").parent_id,
            self.env.ref("account.menu_finance_receivables"),
        )
        self.assertEqual(
            self.env.ref("school_finance.menu_school_finance_configuration").parent_id,
            self.env.ref("account.menu_finance_configuration"),
        )
        self.assertEqual(
            english_env.ref("school_finance.menu_school_finance_dashboard").name,
            "School Dashboard",
        )
        self.assertEqual(
            arabic_env.ref("school_finance.menu_school_finance_dashboard").name,
            "لوحة المدرسة",
        )
        self.assertEqual(
            arabic_env["res.lang"]._lang_get("ar_001").direction,
            "rtl",
        )
        settings_fields = self.env["res.config.settings"]._fields
        expected_related = {
            "tax_lock_date": "company_id.tax_lock_date",
            "sale_lock_date": "company_id.sale_lock_date",
            "purchase_lock_date": "company_id.purchase_lock_date",
            "hard_lock_date": "company_id.hard_lock_date",
            "fiscalyear_lock_date": "company_id.fiscalyear_lock_date",
        }
        for field_name, related in expected_related.items():
            self.assertEqual(settings_fields[field_name].related, related)

    def test_followup_subject_default_is_translation_safe(self):
        default = self.env["followup.print"]._fields["email_subject"].default
        self.assertTrue(callable(default))
        self.assertEqual(default(self.env["followup.print"]), "Invoices Reminder")

    def test_invoice_and_receipt_templates_render_school_fields(self):
        invoice = self._create_fee_invoice(term="monthly")
        invoice.action_post()
        invoice_report = self.env.ref("account.account_invoices")
        invoice_html, _ = invoice_report._render_qweb_html(
            invoice_report.report_name,
            invoice.ids,
        )
        self.assertIn(b"TEST Student Automated", invoice_html)
        self.assertIn(b"Academic Period", invoice_html)
        arabic_invoice_html, _ = invoice_report.with_context(
            lang="ar_001"
        )._render_qweb_html(
            invoice_report.report_name,
            invoice.ids,
        )
        self.assertIn("الفترة الدراسية".encode(), arabic_invoice_html)
        self.assertNotIn(b"Academic Period", arabic_invoice_html)

        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "amount": 1000.0,
                    "payment_date": fields.Date.today(),
                    "journal_id": self.bank_journal.id,
                    "school_payment_reference": "TEST-RECEIPT-001",
                }
            )
        )
        payment = wizard._create_payments()
        receipt_report = self.env.ref("account.action_report_payment_receipt")
        receipt_html, _ = receipt_report._render_qweb_html(
            receipt_report.report_name,
            payment.ids,
        )
        self.assertIn(b"TEST-RECEIPT-001", receipt_html)
        arabic_receipt_html, _ = receipt_report.with_context(
            lang="ar_001"
        )._render_qweb_html(
            receipt_report.report_name,
            payment.ids,
        )
        self.assertIn("مرجع المدرسة".encode(), arabic_receipt_html)
        self.assertNotIn(b"School Reference", arabic_receipt_html)
        self.assertIn(b"TEST Student Automated", receipt_html)

    def test_demo_generator_is_guarded_and_tags_created_records(self):
        wizard = self.env["school.finance.demo.generator"].create(
            {"company_id": self.company.id}
        )
        with self.assertRaises(UserError):
            wizard.action_generate()
        wizard.confirm_demo = True
        existing_demo_students = self.env["res.partner"].search(
            [
                ("is_school_student", "=", True),
                ("school_demo_data", "=", True),
            ]
        )
        generated_now = not existing_demo_students
        if generated_now:
            action = wizard.action_generate()
            self.assertEqual(action["res_model"], "school.finance.demo.generator")
        demo_students = self.env["res.partner"].search(
            [
                ("is_school_student", "=", True),
                ("school_demo_data", "=", True),
            ]
        )
        self.assertEqual(len(demo_students), 3)
        self.assertTrue(
            all(name.startswith("[TEST]") for name in demo_students.mapped("name"))
        )
        demo_invoices = self.env["account.move"].search(
            [
                ("school_demo_data", "=", True),
                ("move_type", "=", "out_invoice"),
                ("school_student_id", "!=", False),
            ]
        )
        self.assertEqual(len(demo_invoices), 3)
        if generated_now:
            self.assertEqual(set(demo_invoices.mapped("state")), {"draft"})
