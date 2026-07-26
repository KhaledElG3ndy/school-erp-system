from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models


class SchoolFinanceDashboard(models.TransientModel):
    _name = "school.finance.dashboard"
    _description = "School Finance Dashboard"

    date_from = fields.Date(
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(month=1, day=1),
    )
    date_to = fields.Date(required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    department_id = fields.Many2one(
        "school.department", string="Department / Cost Center", check_company=True
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", readonly=True
    )
    total_revenue = fields.Monetary(compute="_compute_kpis")
    total_expense = fields.Monetary(compute="_compute_kpis")
    net_result = fields.Monetary(compute="_compute_kpis")
    available_cash = fields.Monetary(compute="_compute_kpis")
    bank_balance = fields.Monetary(compute="_compute_kpis")
    cash_box_balance = fields.Monetary(compute="_compute_kpis")
    total_receivable = fields.Monetary(compute="_compute_kpis")
    total_payable = fields.Monetary(compute="_compute_kpis")
    unpaid_student_invoice_count = fields.Integer(compute="_compute_kpis")
    unpaid_student_invoice_amount = fields.Monetary(compute="_compute_kpis")
    overdue_student_invoice_count = fields.Integer(compute="_compute_kpis")
    overdue_student_invoice_amount = fields.Monetary(compute="_compute_kpis")
    due_vendor_bill_count = fields.Integer(compute="_compute_kpis")
    due_vendor_bill_amount = fields.Monetary(compute="_compute_kpis")
    budget_planned = fields.Monetary(compute="_compute_kpis")
    budget_actual = fields.Monetary(compute="_compute_kpis")
    period_line_ids = fields.One2many(
        "school.finance.dashboard.period", "dashboard_id", string="Period Movement"
    )

    def _move_line_domain(
        self, extra=None, date_range=True, department_filter=True
    ):
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("parent_state", "=", "posted"),
        ]
        if date_range:
            domain += [("date", ">=", self.date_from), ("date", "<=", self.date_to)]
        elif self.date_to:
            domain += [("date", "<=", self.date_to)]
        if department_filter and self.department_id.analytic_account_id:
            domain.append(
                (
                    "distribution_analytic_account_ids",
                    "in",
                    self.department_id.analytic_account_id.id,
                )
            )
        return domain + (extra or [])

    def _sum_lines(
        self,
        extra,
        expression="balance",
        date_range=True,
        department_filter=True,
    ):
        lines = self.env["account.move.line"].search(
            self._move_line_domain(
                extra,
                date_range=date_range,
                department_filter=department_filter,
            )
        )
        return sum(lines.mapped(expression))

    @api.depends("date_from", "date_to", "company_id", "department_id")
    def _compute_kpis(self):
        Move = self.env["account.move"]
        BudgetLine = self.env["crossovered.budget.lines"]
        today = fields.Date.context_today(self)
        for dashboard in self:
            if not dashboard.company_id or not dashboard.date_from or not dashboard.date_to:
                dashboard.total_revenue = 0.0
                dashboard.total_expense = 0.0
                dashboard.net_result = 0.0
                dashboard.available_cash = 0.0
                dashboard.bank_balance = 0.0
                dashboard.cash_box_balance = 0.0
                dashboard.total_receivable = 0.0
                dashboard.total_payable = 0.0
                dashboard.unpaid_student_invoice_count = 0
                dashboard.unpaid_student_invoice_amount = 0.0
                dashboard.overdue_student_invoice_count = 0
                dashboard.overdue_student_invoice_amount = 0.0
                dashboard.due_vendor_bill_count = 0
                dashboard.due_vendor_bill_amount = 0.0
                dashboard.budget_planned = 0.0
                dashboard.budget_actual = 0.0
                continue
            revenue_balance = dashboard._sum_lines(
                [("account_id.account_type", "in", ("income", "income_other"))]
            )
            expense_balance = dashboard._sum_lines(
                [
                    (
                        "account_id.account_type",
                        "in",
                        ("expense", "expense_direct_cost", "expense_depreciation"),
                    )
                ]
            )
            dashboard.total_revenue = -revenue_balance
            dashboard.total_expense = expense_balance
            dashboard.net_result = (
                dashboard.total_revenue - dashboard.total_expense
            )
            dashboard.available_cash = dashboard._sum_lines(
                [("account_id.account_type", "=", "asset_cash")],
                date_range=False,
                department_filter=False,
            )
            bank_accounts = self.env["account.journal"].search(
                [
                    ("company_id", "=", dashboard.company_id.id),
                    ("type", "=", "bank"),
                ]
            ).default_account_id
            cash_accounts = self.env["account.journal"].search(
                [
                    ("company_id", "=", dashboard.company_id.id),
                    ("type", "=", "cash"),
                ]
            ).default_account_id
            dashboard.bank_balance = dashboard._sum_lines(
                [("account_id", "in", bank_accounts.ids or [0])],
                date_range=False,
                department_filter=False,
            )
            dashboard.cash_box_balance = dashboard._sum_lines(
                [("account_id", "in", cash_accounts.ids or [0])],
                date_range=False,
                department_filter=False,
            )
            dashboard.total_receivable = dashboard._sum_lines(
                [("account_id.account_type", "=", "asset_receivable")],
                expression="amount_residual",
                date_range=False,
                department_filter=False,
            )
            dashboard.total_payable = -dashboard._sum_lines(
                [("account_id.account_type", "=", "liability_payable")],
                expression="amount_residual",
                date_range=False,
                department_filter=False,
            )
            student_domain = [
                ("company_id", "=", dashboard.company_id.id),
                ("state", "=", "posted"),
                ("move_type", "=", "out_invoice"),
                ("school_student_id", "!=", False),
                ("payment_state", "not in", ("paid", "reversed")),
                ("invoice_date", "<=", dashboard.date_to),
            ]
            if dashboard.department_id:
                student_domain.append(
                    (
                        "invoice_line_ids.school_department_id",
                        "=",
                        dashboard.department_id.id,
                    )
                )
            student_invoices = Move.search(student_domain)
            overdue_date = min(today, dashboard.date_to)
            overdue_invoices = student_invoices.filtered(
                lambda move: move.invoice_date_due
                and move.invoice_date_due < overdue_date
                and move.amount_residual > 0
            )
            dashboard.unpaid_student_invoice_count = len(student_invoices)
            dashboard.unpaid_student_invoice_amount = sum(
                student_invoices.mapped("school_collection_residual")
            )
            dashboard.overdue_student_invoice_count = len(overdue_invoices)
            dashboard.overdue_student_invoice_amount = sum(
                overdue_invoices.mapped("school_collection_residual")
            )
            vendor_bills = Move.search(
                [
                    ("company_id", "=", dashboard.company_id.id),
                    ("state", "=", "posted"),
                    ("move_type", "=", "in_invoice"),
                    ("payment_state", "not in", ("paid", "reversed")),
                    ("invoice_date_due", "<=", overdue_date),
                ]
            )
            dashboard.due_vendor_bill_count = len(vendor_bills)
            dashboard.due_vendor_bill_amount = sum(
                vendor_bills.mapped("amount_residual")
            )
            budget_domain = [
                ("company_id", "=", dashboard.company_id.id),
                ("date_from", "<=", dashboard.date_to),
                ("date_to", ">=", dashboard.date_from),
                ("crossovered_budget_state", "in", ("validate", "done")),
            ]
            if dashboard.department_id.analytic_account_id:
                budget_domain.append(
                    (
                        "analytic_account_id",
                        "=",
                        dashboard.department_id.analytic_account_id.id,
                    )
                )
            budget_lines = BudgetLine.search(budget_domain)
            dashboard.budget_planned = sum(budget_lines.mapped("planned_amount"))
            dashboard.budget_actual = sum(budget_lines.mapped("practical_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        dashboards = super().create(vals_list)
        dashboards._refresh_period_lines()
        return dashboards

    def _refresh_period_lines(self):
        Period = self.env["school.finance.dashboard.period"]
        for dashboard in self:
            dashboard.period_line_ids.unlink()
            if not dashboard.date_from or not dashboard.date_to:
                continue
            cursor = dashboard.date_from.replace(day=1)
            commands = []
            while cursor <= dashboard.date_to:
                month_end = min(cursor + relativedelta(months=1, days=-1), dashboard.date_to)
                month_start = max(cursor, dashboard.date_from)
                base_domain = [
                    ("company_id", "=", dashboard.company_id.id),
                    ("parent_state", "=", "posted"),
                    ("date", ">=", month_start),
                    ("date", "<=", month_end),
                ]
                if dashboard.department_id.analytic_account_id:
                    base_domain.append(
                        (
                            "distribution_analytic_account_ids",
                            "in",
                            dashboard.department_id.analytic_account_id.id,
                        )
                    )
                lines = self.env["account.move.line"].search(base_domain)
                revenue = -sum(
                    lines.filtered(
                        lambda line: line.account_id.account_type
                        in ("income", "income_other")
                    ).mapped("balance")
                )
                expense = sum(
                    lines.filtered(
                        lambda line: line.account_id.account_type
                        in ("expense", "expense_direct_cost", "expense_depreciation")
                    ).mapped("balance")
                )
                commands.append(
                    fields.Command.create(
                        {
                            "name": cursor.strftime("%Y-%m"),
                            "date_from": month_start,
                            "date_to": month_end,
                            "revenue": revenue,
                            "expense": expense,
                        }
                    )
                )
                cursor += relativedelta(months=1)
            dashboard.period_line_ids = commands
        return Period

    def action_refresh(self):
        self.ensure_one()
        self._refresh_period_lines()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def _open_moves(self, name, domain):
        self.ensure_one()
        return {
            "name": name,
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": domain,
        }

    def action_open_student_invoices(self):
        return self._open_moves(
            _("Unpaid Student Invoices"),
            [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "posted"),
                ("move_type", "=", "out_invoice"),
                ("school_student_id", "!=", False),
                ("payment_state", "not in", ("paid", "reversed")),
            ],
        )

    def action_open_overdue_student_invoices(self):
        return self._open_moves(
            _("Overdue Student Invoices"),
            [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "posted"),
                ("move_type", "=", "out_invoice"),
                ("school_student_id", "!=", False),
                ("payment_state", "not in", ("paid", "reversed")),
                ("invoice_date_due", "<", min(fields.Date.context_today(self), self.date_to)),
            ],
        )

    def action_open_vendor_bills(self):
        return self._open_moves(
            _("Due Vendor Bills"),
            [
                ("company_id", "=", self.company_id.id),
                ("state", "=", "posted"),
                ("move_type", "=", "in_invoice"),
                ("payment_state", "not in", ("paid", "reversed")),
            ],
        )

    def action_open_budget(self):
        self.ensure_one()
        return {
            "name": _("Budgets"),
            "type": "ir.actions.act_window",
            "res_model": "crossovered.budget",
            "view_mode": "list,form",
            "domain": [("company_id", "=", self.company_id.id)],
        }

    def action_open_journal_items(self):
        self.ensure_one()
        return {
            "name": _("Posted Journal Items"),
            "type": "ir.actions.act_window",
            "res_model": "account.move.line",
            "view_mode": "list,form",
            "domain": self._move_line_domain(),
        }


class SchoolFinanceDashboardPeriod(models.TransientModel):
    _name = "school.finance.dashboard.period"
    _description = "School Finance Dashboard Period"
    _order = "date_from"

    dashboard_id = fields.Many2one(
        "school.finance.dashboard", required=True, ondelete="cascade"
    )
    name = fields.Char(required=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    revenue = fields.Monetary()
    expense = fields.Monetary()
    net_result = fields.Monetary(compute="_compute_net_result")
    currency_id = fields.Many2one(
        related="dashboard_id.currency_id", readonly=True
    )

    @api.depends("revenue", "expense")
    def _compute_net_result(self):
        for line in self:
            line.net_result = line.revenue - line.expense
