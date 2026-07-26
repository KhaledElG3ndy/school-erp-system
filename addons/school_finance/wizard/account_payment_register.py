from odoo import api, fields, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    school_student_id = fields.Many2one(
        "res.partner",
        string="Student",
        compute="_compute_school_payment_context",
        store=True,
        readonly=False,
        domain="[('is_school_student', '=', True)]",
    )
    school_guardian_id = fields.Many2one(
        "res.partner",
        string="Guardian",
        compute="_compute_school_payment_context",
        store=True,
        readonly=False,
        domain="[('is_school_guardian', '=', True)]",
    )
    school_payment_reference = fields.Char(string="School Payment Reference")

    @api.depends("line_ids")
    def _compute_school_payment_context(self):
        for wizard in self:
            moves = wizard.line_ids.move_id
            wizard.school_student_id = (
                moves.school_student_id
                if len(moves.school_student_id) == 1
                else False
            )
            wizard.school_guardian_id = (
                moves.school_guardian_id
                if len(moves.school_guardian_id) == 1
                else False
            )

    def _school_payment_values(self):
        self.ensure_one()
        return {
            "school_student_id": self.school_student_id.id,
            "school_guardian_id": self.school_guardian_id.id,
            "school_payment_reference": self.school_payment_reference,
            "school_demo_data": any(self.line_ids.move_id.mapped("school_demo_data")),
        }

    def _create_payment_vals_from_wizard(self, batch_result):
        values = super()._create_payment_vals_from_wizard(batch_result)
        values.update(self._school_payment_values())
        return values

    def _create_payment_vals_from_batch(self, batch_result):
        values = super()._create_payment_vals_from_batch(batch_result)
        moves = batch_result["lines"].move_id
        values.update(
            {
                "school_student_id": (
                    moves.school_student_id.id
                    if len(moves.school_student_id) == 1
                    else False
                ),
                "school_guardian_id": (
                    moves.school_guardian_id.id
                    if len(moves.school_guardian_id) == 1
                    else False
                ),
                "school_payment_reference": self.school_payment_reference,
                "school_demo_data": any(moves.mapped("school_demo_data")),
            }
        )
        return values

    def _post_payments(self, to_process, edit_mode=False):
        pending_approval = self.env["account.payment"]
        ready = self.env["account.payment"]
        for values in to_process:
            payment = values["payment"]
            if payment.school_approval_required:
                pending_approval |= payment
            else:
                ready |= payment
        if pending_approval:
            pending_approval.action_school_submit()
        if ready:
            ready.with_context(skip_sale_auto_invoice_send=True).action_post()

    def _reconcile_payments(self, to_process, edit_mode=False):
        ready_values = [
            values
            for values in to_process
            if not values["payment"].school_approval_required
        ]
        if ready_values:
            super()._reconcile_payments(ready_values, edit_mode=edit_mode)
        for values in to_process:
            payment = values["payment"]
            if payment.school_approval_required:
                values["to_reconcile"].move_id.matched_payment_ids = [
                    fields.Command.link(payment.id)
                ]
