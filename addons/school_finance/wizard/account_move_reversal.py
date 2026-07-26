from odoo import _, models
from odoo.exceptions import UserError


class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    def _prepare_default_reversal(self, move):
        values = super()._prepare_default_reversal(move)
        values.update(
            {
                "school_student_id": move.school_student_id.id,
                "school_guardian_id": move.school_guardian_id.id,
                "school_academic_year_id": move.school_academic_year_id.id,
                "school_term": move.school_term,
                "school_installment_plan_id": move.school_installment_plan_id.id,
                "school_refund_reason": self.reason,
                "school_demo_data": move.school_demo_data,
                "school_approval_state": "draft",
            }
        )
        return values

    def reverse_moves(self, is_modify=False):
        if self.move_ids.filtered("school_is_fee_invoice") and not self.reason:
            raise UserError(_("A refund reason is required for school fee credit notes."))
        return super().reverse_moves(is_modify=is_modify)

