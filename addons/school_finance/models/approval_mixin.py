from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SchoolFinanceApprovalMixin(models.AbstractModel):
    _name = "school.finance.approval.mixin"
    _description = "School Finance Approval Workflow"

    school_approval_required = fields.Boolean(
        string="Approval Required",
        compute="_compute_school_approval_required",
        store=True,
    )
    school_approval_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("reviewed", "Reviewed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("returned", "Returned for Correction"),
        ],
        string="Finance Approval",
        default="draft",
        copy=False,
        tracking=True,
    )
    school_submitted_by_id = fields.Many2one(
        "res.users", string="Submitted By", readonly=True, copy=False, tracking=True
    )
    school_submitted_date = fields.Datetime(
        string="Submission Date", readonly=True, copy=False, tracking=True
    )
    school_reviewed_by_id = fields.Many2one(
        "res.users", string="Reviewed By", readonly=True, copy=False, tracking=True
    )
    school_reviewed_date = fields.Datetime(
        string="Review Date", readonly=True, copy=False, tracking=True
    )
    school_approved_by_id = fields.Many2one(
        "res.users", string="Approved By", readonly=True, copy=False, tracking=True
    )
    school_approved_date = fields.Datetime(
        string="Approval Date", readonly=True, copy=False, tracking=True
    )
    school_approval_reason = fields.Text(
        string="Rejection / Return Reason", copy=False, tracking=True
    )

    @api.depends("company_id")
    def _compute_school_approval_required(self):
        for record in self:
            record.school_approval_required = record._school_requires_approval()

    def _school_requires_approval(self):
        self.ensure_one()
        return False

    def _school_message(self, body):
        for record in self:
            if hasattr(record, "message_post"):
                record.message_post(body=body)

    def _school_check_group(self, xmlid, message):
        if not self.env.user.has_group(xmlid):
            raise AccessError(message)

    def _school_check_approved(self):
        pending = self.filtered(
            lambda record: record.school_approval_required
            and record.school_approval_state != "approved"
        )
        if pending:
            raise UserError(
                _(
                    "Finance approval must be completed before this document can be posted or validated."
                )
            )

    def action_school_submit(self):
        invalid = self.filtered(
            lambda record: not record.school_approval_required
            or record.school_approval_state not in ("draft", "returned", "rejected")
        )
        if invalid:
            raise UserError(_("Only a draft document requiring approval can be submitted."))
        now = fields.Datetime.now()
        self.write(
            {
                "school_approval_state": "submitted",
                "school_submitted_by_id": self.env.user.id,
                "school_submitted_date": now,
                "school_reviewed_by_id": False,
                "school_reviewed_date": False,
                "school_approved_by_id": False,
                "school_approved_date": False,
                "school_approval_reason": False,
            }
        )
        self._school_message(_("Document submitted for finance review."))
        return True

    def action_school_review(self):
        self._school_check_group(
            "school_finance.group_school_finance_reviewer",
            _("Only a finance reviewer can review this document."),
        )
        if any(record.school_approval_state != "submitted" for record in self):
            raise UserError(_("Only submitted documents can be reviewed."))
        now = fields.Datetime.now()
        self.write(
            {
                "school_approval_state": "reviewed",
                "school_reviewed_by_id": self.env.user.id,
                "school_reviewed_date": now,
                "school_approval_reason": False,
            }
        )
        self._school_message(_("Document reviewed and sent for approval."))
        return True

    def action_school_approve(self):
        self._school_check_group(
            "school_finance.group_school_finance_approver",
            _("Only a finance approver can approve this document."),
        )
        if any(record.school_approval_state != "reviewed" for record in self):
            raise UserError(_("Only reviewed documents can be approved."))
        if any(
            record.company_id.school_prevent_self_approval
            and record.create_uid == self.env.user
            for record in self
        ):
            raise UserError(_("You cannot approve a document that you created."))
        now = fields.Datetime.now()
        self.write(
            {
                "school_approval_state": "approved",
                "school_approved_by_id": self.env.user.id,
                "school_approved_date": now,
                "school_approval_reason": False,
            }
        )
        self._school_message(_("Document approved for posting or validation."))
        return True

    def action_school_reject(self):
        self._school_check_group(
            "school_finance.group_school_finance_reviewer",
            _("Only a finance reviewer can reject this document."),
        )
        if any(
            record.school_approval_state not in ("submitted", "reviewed")
            for record in self
        ):
            raise UserError(_("Only submitted or reviewed documents can be rejected."))
        if any(not record.school_approval_reason for record in self):
            raise UserError(_("Enter a rejection reason before rejecting the document."))
        self.write({"school_approval_state": "rejected"})
        self._school_message(_("Document rejected: %s") % self[0].school_approval_reason)
        return True

    def action_school_return(self):
        self._school_check_group(
            "school_finance.group_school_finance_reviewer",
            _("Only a finance reviewer can return this document."),
        )
        if any(
            record.school_approval_state not in ("submitted", "reviewed", "approved")
            for record in self
        ):
            raise UserError(
                _("Only submitted, reviewed or approved documents can be returned.")
            )
        if any(not record.school_approval_reason for record in self):
            raise UserError(_("Enter a return reason before returning the document."))
        self.write(
            {
                "school_approval_state": "returned",
                "school_approved_by_id": False,
                "school_approved_date": False,
            }
        )
        self._school_message(
            _("Document returned for correction: %s")
            % self[0].school_approval_reason
        )
        return True
