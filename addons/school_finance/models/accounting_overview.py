from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    @api.model
    def _school_overview_check_access(self):
        if not self.env.user.has_group(
            "school_finance.group_school_finance_entry"
        ):
            raise AccessError(
                _("You are not allowed to access the school accounting overview.")
            )

    @api.model
    def _school_overview_filters(self, values=None):
        values = values or {}
        today = fields.Date.context_today(self)
        date_from = fields.Date.to_date(values.get("date_from"))
        date_to = fields.Date.to_date(values.get("date_to"))
        date_from = date_from or today.replace(month=1, day=1)
        date_to = date_to or today
        if date_from > date_to:
            raise ValidationError(_("The start date must be before the end date."))

        try:
            company_id = int(values.get("company_id") or self.env.company.id)
        except (TypeError, ValueError):
            raise ValidationError(_("Select a valid company.")) from None
        company = self.env["res.company"].browse(company_id).exists()
        if not company or company not in self.env.companies:
            raise AccessError(_("You are not allowed to access this company."))

        analytic_account = self.env["account.analytic.account"]
        if values.get("analytic_account_id"):
            try:
                analytic_id = int(values["analytic_account_id"])
            except (TypeError, ValueError):
                raise ValidationError(_("Select a valid cost center.")) from None
            analytic_account = (
                self.env["account.analytic.account"].browse(analytic_id).exists()
            )
            if not analytic_account or (
                analytic_account.company_id
                and analytic_account.company_id != company
            ):
                raise AccessError(_("You are not allowed to access this cost center."))

        return {
            "date_from": date_from,
            "date_to": date_to,
            "company": company,
            "analytic_account": analytic_account,
        }

    @api.model
    def _school_overview_line_domain(
        self,
        filters,
        extra=None,
        include_date_from=True,
        include_analytic=True,
    ):
        domain = [
            ("company_id", "=", filters["company"].id),
            ("parent_state", "=", "posted"),
            ("date", "<=", filters["date_to"]),
        ]
        if include_date_from:
            domain.append(("date", ">=", filters["date_from"]))
        if include_analytic and filters["analytic_account"]:
            domain.append(
                (
                    "distribution_analytic_account_ids",
                    "in",
                    filters["analytic_account"].id,
                )
            )
        return domain + (extra or [])

    @api.model
    def _school_overview_sum(self, domain, field_name="balance"):
        grouped = self._read_group(
            domain,
            aggregates=[f"{field_name}:sum"],
        )
        return float(grouped[0][0] or 0.0) if grouped else 0.0

    @api.model
    def _school_overview_move_domain(
        self, filters, move_types, extra=None, include_date_from=True
    ):
        domain = [
            ("company_id", "=", filters["company"].id),
            ("state", "=", "posted"),
            ("move_type", "in", move_types),
            ("invoice_date", "<=", filters["date_to"]),
        ]
        if include_date_from:
            domain.append(("invoice_date", ">=", filters["date_from"]))
        if filters["analytic_account"]:
            domain.append(
                (
                    "invoice_line_ids.distribution_analytic_account_ids",
                    "in",
                    filters["analytic_account"].id,
                )
            )
        return domain + (extra or [])

    @api.model
    def _school_overview_residual(self, moves, field_name):
        company = moves[:1].company_id or self.env.company
        total = 0.0
        for move in moves:
            amount = max(move[field_name], 0.0)
            total += move.currency_id._convert(
                amount,
                company.currency_id,
                company,
                move.invoice_date or fields.Date.context_today(self),
            )
        return total

    @api.model
    def _school_overview_prepare_action(self, action):
        action["views"] = [
            [False, view_type]
            for view_type in action["view_mode"].split(",")
        ]
        return action

    @api.model
    def _school_overview_monthly_values(self, filters):
        chart_start = filters["date_from"].replace(day=1)
        chart_end = filters["date_to"].replace(day=1)
        months = []
        cursor = chart_start
        while cursor <= chart_end:
            months.append(cursor)
            cursor += relativedelta(months=1)
        truncated = len(months) > 18
        months = months[-18:]

        income_types = ("income", "income_other")
        expense_types = (
            "expense",
            "expense_direct_cost",
            "expense_depreciation",
        )
        values = []
        for month_start in months:
            month_end = min(
                month_start + relativedelta(months=1, days=-1),
                filters["date_to"],
            )
            effective_start = max(month_start, filters["date_from"])
            base_domain = self._school_overview_line_domain(filters)
            base_domain = [
                item
                for item in base_domain
                if not (
                    isinstance(item, (tuple, list))
                    and item[0] == "date"
                )
            ]
            base_domain += [
                ("date", ">=", effective_start),
                ("date", "<=", month_end),
            ]
            revenue = -self._school_overview_sum(
                base_domain
                + [("account_id.account_type", "in", income_types)]
            )
            expense = self._school_overview_sum(
                base_domain
                + [("account_id.account_type", "in", expense_types)]
            )
            values.append(
                {
                    "key": month_start.strftime("%Y-%m"),
                    "revenue": revenue,
                    "expense": expense,
                    "net_result": revenue - expense,
                }
            )
        return values, truncated

    @api.model
    def get_school_accounting_overview(self, values=None):
        self._school_overview_check_access()
        filters = self._school_overview_filters(values)
        company = filters["company"]
        income_types = ("income", "income_other")
        expense_types = (
            "expense",
            "expense_direct_cost",
            "expense_depreciation",
        )

        revenue = -self._school_overview_sum(
            self._school_overview_line_domain(
                filters,
                [("account_id.account_type", "in", income_types)],
            )
        )
        expenses = self._school_overview_sum(
            self._school_overview_line_domain(
                filters,
                [("account_id.account_type", "in", expense_types)],
            )
        )

        journals = self.env["account.journal"].search(
            [
                ("company_id", "=", company.id),
                ("type", "in", ("bank", "cash")),
            ]
        )
        bank_accounts = journals.filtered(
            lambda journal: journal.type == "bank"
        ).default_account_id
        cash_accounts = journals.filtered(
            lambda journal: journal.type == "cash"
        ).default_account_id
        bank_balance = self._school_overview_sum(
            self._school_overview_line_domain(
                filters,
                [("account_id", "in", bank_accounts.ids or [0])],
                include_date_from=False,
                include_analytic=False,
            )
        )
        cash_balance = self._school_overview_sum(
            self._school_overview_line_domain(
                filters,
                [("account_id", "in", cash_accounts.ids or [0])],
                include_date_from=False,
                include_analytic=False,
            )
        )
        receivables = self._school_overview_sum(
            self._school_overview_line_domain(
                filters,
                [("account_id.account_type", "=", "asset_receivable")],
                include_date_from=False,
                include_analytic=False,
            ),
            "amount_residual",
        )
        payables = -self._school_overview_sum(
            self._school_overview_line_domain(
                filters,
                [("account_id.account_type", "=", "liability_payable")],
                include_date_from=False,
                include_analytic=False,
            ),
            "amount_residual",
        )

        student_domain = self._school_overview_move_domain(
            filters,
            ("out_invoice",),
            [
                ("school_student_id", "!=", False),
                ("payment_state", "not in", ("paid", "reversed")),
            ],
        )
        student_invoices = self.env["account.move"].search(student_domain)
        as_of_date = min(fields.Date.context_today(self), filters["date_to"])
        overdue_student_invoices = student_invoices.filtered(
            lambda move: move.invoice_date_due
            and move.invoice_date_due < as_of_date
            and move.school_collection_residual > 0
        )
        vendor_bills = self.env["account.move"].search(
            self._school_overview_move_domain(
                filters,
                ("in_invoice",),
                [
                    ("payment_state", "not in", ("paid", "reversed")),
                    ("invoice_date_due", "<=", as_of_date),
                ],
            )
        )

        budget_domain = [
            ("company_id", "=", company.id),
            ("date_from", "<=", filters["date_to"]),
            ("date_to", ">=", filters["date_from"]),
            ("crossovered_budget_state", "in", ("validate", "done")),
        ]
        if filters["analytic_account"]:
            budget_domain.append(
                ("analytic_account_id", "=", filters["analytic_account"].id)
            )
        budget_lines = self.env["crossovered.budget.lines"].search(budget_domain)
        budget_planned = sum(budget_lines.mapped("planned_amount"))
        budget_actual = sum(budget_lines.mapped("practical_amount"))

        movement, movement_truncated = self._school_overview_monthly_values(
            filters
        )
        analytic_accounts = self.env["account.analytic.account"].search(
            [
                ("company_id", "in", (False, company.id)),
            ],
            order="name",
        )
        lang = self.env["res.lang"]._lang_get(self.env.lang)
        return {
            "filters": {
                "date_from": fields.Date.to_string(filters["date_from"]),
                "date_to": fields.Date.to_string(filters["date_to"]),
                "company_id": company.id,
                "analytic_account_id": filters["analytic_account"].id or False,
            },
            "options": {
                "companies": [
                    {"id": item.id, "name": item.display_name}
                    for item in self.env.companies
                ],
                "analytic_accounts": [
                    {"id": item.id, "name": item.display_name}
                    for item in analytic_accounts
                ],
            },
            "currency_id": company.currency_id.id,
            "currency_code": company.currency_id.name,
            "direction": lang.direction,
            "kpis": {
                "revenue": revenue,
                "expenses": expenses,
                "net_result": revenue - expenses,
                "available_cash": bank_balance + cash_balance,
                "bank_balance": bank_balance,
                "cash_balance": cash_balance,
                "receivables": receivables,
                "payables": payables,
                "unpaid_student_invoice_count": len(student_invoices),
                "unpaid_student_invoice_amount": self._school_overview_residual(
                    student_invoices, "school_collection_residual"
                ),
                "overdue_student_invoice_count": len(
                    overdue_student_invoices
                ),
                "overdue_student_invoice_amount": self._school_overview_residual(
                    overdue_student_invoices, "school_collection_residual"
                ),
                "due_vendor_bill_count": len(vendor_bills),
                "due_vendor_bill_amount": self._school_overview_residual(
                    vendor_bills, "amount_residual"
                ),
                "budget_planned": budget_planned,
                "budget_actual": budget_actual,
            },
            "charts": {
                "movement": movement,
                "movement_truncated": movement_truncated,
                "liquidity": {
                    "bank": bank_balance,
                    "cash": cash_balance,
                },
            },
        }

    @api.model
    def open_school_accounting_overview_target(self, target, values=None):
        self._school_overview_check_access()
        filters = self._school_overview_filters(values)
        company = filters["company"]
        income_types = ("income", "income_other")
        expense_types = (
            "expense",
            "expense_direct_cost",
            "expense_depreciation",
        )

        action = {
            "type": "ir.actions.act_window",
            "target": "current",
        }
        if target in {
            "revenue",
            "expenses",
            "net_result",
            "available_cash",
            "receivables",
            "payables",
        }:
            extra = []
            include_date_from = True
            include_analytic = True
            if target == "revenue":
                extra = [("account_id.account_type", "in", income_types)]
            elif target == "expenses":
                extra = [("account_id.account_type", "in", expense_types)]
            elif target == "net_result":
                extra = [
                    (
                        "account_id.account_type",
                        "in",
                        income_types + expense_types,
                    )
                ]
            elif target == "available_cash":
                journal_accounts = self.env["account.journal"].search(
                    [
                        ("company_id", "=", company.id),
                        ("type", "in", ("bank", "cash")),
                    ]
                ).default_account_id
                extra = [("account_id", "in", journal_accounts.ids or [0])]
                include_date_from = False
                include_analytic = False
            elif target == "receivables":
                extra = [
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("amount_residual", "!=", 0),
                ]
                include_date_from = False
                include_analytic = False
            elif target == "payables":
                extra = [
                    ("account_id.account_type", "=", "liability_payable"),
                    ("amount_residual", "!=", 0),
                ]
                include_date_from = False
                include_analytic = False
            action.update(
                {
                    "name": {
                        "revenue": _("Revenue Journal Items"),
                        "expenses": _("Expense Journal Items"),
                        "net_result": _("Profit and Loss Journal Items"),
                        "available_cash": _("Bank and Cash Journal Items"),
                        "receivables": _("Open Receivable Journal Items"),
                        "payables": _("Open Payable Journal Items"),
                    }[target],
                    "res_model": "account.move.line",
                    "view_mode": "list,form",
                    "domain": self._school_overview_line_domain(
                        filters,
                        extra,
                        include_date_from=include_date_from,
                        include_analytic=include_analytic,
                    ),
                }
            )
            return self._school_overview_prepare_action(action)

        if target in {
            "student_invoices",
            "overdue_student_invoices",
            "due_vendor_bills",
            "vendor_bills",
            "customer_invoices",
        }:
            if target in {"student_invoices", "overdue_student_invoices"}:
                move_types = ("out_invoice",)
                extra = [
                    ("school_student_id", "!=", False),
                    ("payment_state", "not in", ("paid", "reversed")),
                ]
                if target == "overdue_student_invoices":
                    extra.append(
                        (
                            "invoice_date_due",
                            "<",
                            min(
                                fields.Date.context_today(self),
                                filters["date_to"],
                            ),
                        )
                    )
            elif target == "due_vendor_bills":
                move_types = ("in_invoice",)
                extra = [
                    ("payment_state", "not in", ("paid", "reversed")),
                    (
                        "invoice_date_due",
                        "<=",
                        min(
                            fields.Date.context_today(self),
                            filters["date_to"],
                        ),
                    ),
                ]
            elif target == "vendor_bills":
                move_types = ("in_invoice", "in_refund")
                extra = []
            else:
                move_types = ("out_invoice", "out_refund")
                extra = []
            action.update(
                {
                    "name": {
                        "student_invoices": _("Unpaid Student Invoices"),
                        "overdue_student_invoices": _(
                            "Overdue Student Invoices"
                        ),
                        "due_vendor_bills": _("Due Vendor Bills"),
                        "vendor_bills": _("Vendor Bills"),
                        "customer_invoices": _("Customer Invoices"),
                    }[target],
                    "res_model": "account.move",
                    "view_mode": "list,kanban,form",
                    "domain": self._school_overview_move_domain(
                        filters, move_types, extra
                    ),
                    "context": {
                        "default_move_type": (
                            "in_invoice"
                            if target in {"due_vendor_bills", "vendor_bills"}
                            else "out_invoice"
                        )
                    },
                }
            )
            return self._school_overview_prepare_action(action)

        simple_targets = {
            "payments": {
                "name": _("Payments"),
                "res_model": "account.payment",
                "view_mode": "list,kanban,form,graph",
                "domain": [
                    ("company_id", "=", company.id),
                    ("date", ">=", filters["date_from"]),
                    ("date", "<=", filters["date_to"]),
                ],
            },
            "bank_journals": {
                "name": _("Bank Journals"),
                "res_model": "account.journal",
                "view_mode": "kanban,list,form",
                "domain": [
                    ("company_id", "=", company.id),
                    ("type", "=", "bank"),
                ],
            },
            "cash_journals": {
                "name": _("Cash Journals"),
                "res_model": "account.journal",
                "view_mode": "kanban,list,form",
                "domain": [
                    ("company_id", "=", company.id),
                    ("type", "=", "cash"),
                ],
            },
            "journal_entries": {
                "name": _("Journal Entries"),
                "res_model": "account.move",
                "view_mode": "list,form",
                "domain": [
                    ("company_id", "=", company.id),
                    ("move_type", "=", "entry"),
                    ("date", ">=", filters["date_from"]),
                    ("date", "<=", filters["date_to"]),
                ],
            },
            "budgets": {
                "name": _("Budgets"),
                "res_model": "crossovered.budget",
                "view_mode": "list,form",
                "domain": [("company_id", "=", company.id)],
            },
            "assets": {
                "name": _("Assets"),
                "res_model": "account.asset.asset",
                "view_mode": "list,form",
                "domain": [("company_id", "=", company.id)],
            },
        }
        if target not in simple_targets:
            raise ValidationError(_("The requested accounting view is not available."))
        action.update(simple_targets[target])
        return self._school_overview_prepare_action(action)
