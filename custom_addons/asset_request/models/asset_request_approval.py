from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AssetRequestApproval(models.Model):
    _name = 'asset.request.approval'
    _description = 'Asset Request Approval'
    _order = 'request_id, approval_round, sequence'

    request_id = fields.Many2one(
        'asset.request',
        string='Request',
        required=True,
        ondelete='cascade',
    )
    
    approval_level = fields.Integer(
        string='Level',
        required=True,
        readonly=True,
    )
    
    sequence = fields.Integer(
        string='Sequence',
        required=True,
        default=1,
        readonly=True,
    )

    approval_round = fields.Integer(
        string='Approval Round',
        required=True,
        default=1,
        readonly=True,
    )

    approval_label = fields.Char(
        string='Level Label',
        compute='_compute_approval_label',
        store=False,
    )

    current_approver_id = fields.Many2one(
        'res.users',
        string='Current Approver',
        compute='_compute_current_approver',
        store=False,
    )

    display_approver_id = fields.Many2one(
        'res.users',
        string='Approver',
        compute='_compute_display_approver',
        store=False,
    )
    
    approver_id = fields.Many2one(
        'res.users',
        string='Configured Approver',
        required=True,
    )
    
    status = fields.Selection(
        [
            ('waiting', 'Waiting'),
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='waiting',
        required=True,
        readonly=True,
    )
    
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
    )

    reject_date = fields.Datetime(
        string='Reject Date',
        readonly=True,
    )

    reject_notes = fields.Text(
        string='Reject Notes'
    )

    reject_attachment_ids = fields.Many2many(
        'ir.attachment',
        'asset_request_approval_attachment_rel',
        'approval_id',
        'attachment_id',
        string='Reject Attachments'
    )
    
    notification_sent = fields.Boolean(
        string='Notification Sent',
        default=False,
        readonly=True,
    )

    @api.depends('approval_level')
    def _compute_approval_label(self):
        for rec in self:
            if rec.approval_level == 1:
                rec.approval_label = 'L1 - Manager'
            elif rec.approval_level == 2:
                rec.approval_label = 'L2 - Sr. Manager'
            elif rec.approval_level == 3:
                rec.approval_label = 'L3 - Director'
            else:
                rec.approval_label = 'L%s' % rec.approval_level

    @api.depends('approver_id')
    def _compute_current_approver(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.approver_id:
                rec.current_approver_id = False
                continue
            active_delegation = self.env['asset.request.approval.delegation'].search([
                ('approver_id', '=', rec.approver_id.id),
                ('state', '=', 'active'),
                ('date_from', '<=', today),
                ('date_to', '>=', today),
            ], limit=1)
            rec.current_approver_id = active_delegation.delegate_to_id if active_delegation else rec.approver_id

    @api.depends('current_approver_id', 'approver_id')
    def _compute_display_approver(self):
        for rec in self:
            rec.display_approver_id = rec.current_approver_id or rec.approver_id

    def action_approve(self):
        """Dipanggil dari tombol Approve"""
        self.write({
            'status': 'approved',
            'approval_date': fields.Datetime.now(),
            'reject_date': False,
        })
    
    def action_reject(self):
        """Dipanggil dari tombol Reject"""
        self.write({
            'status': 'rejected',
            'approval_date': False,
            'reject_date': fields.Datetime.now(),
        })
    
    def action_cancel(self):
        self.write({'status': 'cancelled'})
    
    def action_set_pending(self):
        self.write({'status': 'pending'})
    
    def _send_notification(self):
        """Send initial notification to Inbox"""
        for approval in self:
            if approval.status == 'pending' and not approval.notification_sent:
                try:
                    recipient = approval.current_approver_id or approval.approver_id
                    
                    # Buat link manual
                    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    # Cari action ID untuk asset.request
                    action = self.env['ir.actions.act_window'].search([
                        ('res_model', '=', 'asset.request'),
                        ('binding_model_id', '=', False)
                    ], limit=1)
                    action_id = action.id if action else 263
                    request_url = f"{base_url}/odoo/action-{action_id}/{approval.request_id.id}"
                    
                    approval.request_id.activity_schedule(
                        'mail.mail_activity_data_notification',
                        user_id=recipient.id,
                        summary=_('Asset Request Approval Required - Level %d') % approval.approval_level,
                        note=_('Please approve asset request: %s\n\nOpen: %s') % (
                            approval.request_id.name,
                            request_url
                        ),
                        date_deadline=fields.Date.today()
                    )
                    approval.write({
                        'notification_sent': True,
                        'last_reminder_date': fields.Datetime.now(),
                    })
                except Exception as e:
                    _logger.error('Failed to send notification: %s', str(e))

    def _send_reminder(self):
        """Send reminder notification (called by cron job) to Inbox"""
        for approval in self:
            if approval.status == 'pending':
                try:
                    recipient = approval.current_approver_id or approval.approver_id
                    
                    # Buat link manual
                    base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
                    action = self.env['ir.actions.act_window'].search([
                        ('res_model', '=', 'asset.request'),
                        ('binding_model_id', '=', False)
                    ], limit=1)
                    action_id = action.id if action else 263
                    request_url = f"{base_url}/odoo/action-{action_id}/{approval.request_id.id}"
                    
                    approval.request_id.activity_schedule(
                        'mail.mail_activity_data_notification',
                        user_id=recipient.id,
                        summary=_('REMINDER: Asset Request Approval Required - Level %d') % approval.approval_level,
                        note=_('Reminder: Please approve asset request: %s (Request #%s)\n\nOpen: %s') % (
                            approval.request_id.name,
                            approval.request_id.display_name,
                            request_url
                        ),
                        date_deadline=fields.Date.today()
                    )
                    approval.write({
                        'reminder_count': approval.reminder_count + 1,
                        'last_reminder_date': fields.Datetime.now(),
                    })
                    _logger.info('Reminder #%d sent to %s for request %s', 
                                approval.reminder_count + 1, recipient.name, approval.request_id.name)
                except Exception as e:
                    _logger.error('Failed to send reminder: %s', str(e))
    
    def write(self, vals):
        """Approval lines are effectively read-only except for workflow-driven status changes."""
        allowed_keys = {
            'status', 'approval_date', 'reject_date', 'reject_notes', 'reject_attachment_ids', 'notification_sent'
        }
        is_approval_action = set(vals.keys()).issubset(allowed_keys)

        if is_approval_action:
            return super().write(vals)

        raise UserError(_('Approval line records cannot be manually edited. Use the approval workflow or delegation to update approvals.'))