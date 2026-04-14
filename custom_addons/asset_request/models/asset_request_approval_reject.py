from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AssetRequestApprovalReject(models.TransientModel):
    _name = 'asset.request.approval.reject'
    _description = 'Reject Asset Request Approval'

    request_id = fields.Many2one(
        'asset.request',
        string='Request',
        readonly=True,
    )

    approval_id = fields.Many2one(
        'asset.request.approval',
        string='Approval Line',
        readonly=True,
    )

    reject_notes = fields.Text(
        string='Reject Notes',
        required=True,
    )

    reject_attachment_ids = fields.Many2many(
        'ir.attachment',
        'asset_request_approval_reject_attachment_rel',
        'reject_id',
        'attachment_id',
        string='Reject Attachments',
    )

    def action_confirm_reject(self):
        self.ensure_one()

        approval = self.approval_id
        if not approval or approval.status != 'pending':
            raise UserError(_('No pending approval line to reject.'))

        request = approval.request_id
        request._reject_pending_approval(approval, notes=self.reject_notes, attachments=self.reject_attachment_ids)

        return {
            'type': 'ir.actions.act_window_close'
        }
