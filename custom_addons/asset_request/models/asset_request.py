from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class AssetRequest(models.Model):
    _name = 'asset.request'
    _description = 'Asset Request Form'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Request Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer/Partner',
        required=True,
    )

    date_display = fields.Char(
        string='Date ',
        compute='_compute_display_dates',
        store=False,
    )

    required_date_display = fields.Char(
        string='Required ',
        compute='_compute_display_dates',
        store=False,
    )

    type_of_request = fields.Selection(
        [
            ('replacement_temporary', 'Replacement Car - Temporary'),
            ('replacement_new', 'Replacement Car - New'),
        ],
        string='Type of Request',
        required=True,
    )
    required_date = fields.Date(
        string='Required Date',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('new', 'New'),
            ('waiting_approval', 'Waiting for Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status',
        default='new',
        required=True,
        readonly=True
    )

    can_set_draft = fields.Boolean(
        string='Can Set to Draft',
        compute='_compute_can_set_draft',
        store=False
    )

    line_ids = fields.One2many(
        'asset.request.line',
        'request_id',
        string='Request Lines',
    )

    approval_line_ids = fields.One2many(
        'asset.request.approval',
        'request_id',
        string='Approval Lines',
    )

    notes = fields.Text(string='Notes')
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string='Attachments'
    )

    max_approval_level = fields.Integer(
        string='Max Approval Level',
        compute='_compute_approval_level',
        store=True
    )
    current_approval_level = fields.Integer(
        string='Current Approval Level',
        default=0,
    )
    approval_round = fields.Integer(
        string='Approval Round',
        default=1,
        readonly=True,
    )

    # Field untuk kontrol tombol
    can_approve = fields.Boolean(
        string='Can Approve',
        compute='_compute_can_approve',
        store=False
    )
    can_reject = fields.Boolean(
        string='Can Reject',
        compute='_compute_can_reject',
        store=False
    )

    # Field untuk kontrol readonly di line_ids
    line_readonly = fields.Boolean(
        string='Line Readonly',
        compute='_compute_line_readonly',
        store=False
    )

    @api.depends('line_ids', 'line_ids.quantity', 'line_ids.product_brand')
    def _compute_approval_level(self):
        """Compute required approval level based on dynamic rules"""
        for request in self:
            max_level = 1
            config = self.env['asset.approval.config']._get_active_config()

            if not config or not config.rule_ids:
                request.max_approval_level = 1
                continue

            for line in request.line_ids:
                # Cari rule yang cocok untuk line ini (urut berdasarkan sequence)
                matched_rule = False
                for rule in config.rule_ids.sorted('sequence'):
                    # Cek brand
                    if rule.brand_ids:
                        if line.product_brand_id not in rule.brand_ids:
                            continue

                    # Cek quantity
                    if line.quantity > rule.min_quantity:
                        matched_rule = rule
                        break  # Stop di rule pertama yang match

                if matched_rule:
                    level = int(matched_rule.required_level)
                    if level > max_level:
                        max_level = level

            request.max_approval_level = max_level

    @api.depends('date', 'required_date')
    def _compute_display_dates(self):
        for request in self:
            request.date_display = request.date.strftime('%m/%d/%Y') if request.date else ''
            request.required_date_display = request.required_date.strftime('%m/%d/%Y') if request.required_date else ''

    def _get_current_user_pending_approval(self):
        self.ensure_one()
        pending = self._get_current_pending_approval()
        return pending.filtered(lambda a: a.current_approver_id == self.env.user)

    @api.depends('approval_line_ids', 'approval_line_ids.status')
    def _compute_can_approve(self):
        for request in self:
            pending = request._get_current_user_pending_approval()
            request.can_approve = bool(pending)

    @api.depends('approval_line_ids', 'approval_line_ids.status')
    def _compute_can_reject(self):
        for request in self:
            pending = request._get_current_user_pending_approval()
            request.can_reject = bool(pending)

    def _compute_can_set_draft(self):
        for request in self:
            request.can_set_draft = (
                request.state == 'rejected' and
                (request.create_uid == request.env.user or request.env.user.has_group('base.group_system'))
            )

    def _get_approver_from_config(self, level):
        """Get approvers from config (for new request)"""
        config = self.env['asset.approval.config']._get_active_config()

        if not config:
            return self.env.ref('base.user_admin')

        if level == 1:
            approvers = config.level_1_user_ids or config.level_1_user_id
        elif level == 2:
            approvers = config.level_2_user_ids or config.level_2_user_id
        elif level == 3:
            approvers = config.level_3_user_ids or config.level_3_user_id
        else:
            approvers = False

        if not approvers:
            # fallback to administration
            approvers = self.env.ref('base.user_admin')

        return approvers

    def action_submit(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_('Please add at least one line item.'))

        if self.state not in ['new', 'draft', 'rejected']:
            raise ValidationError(_('Only new, draft or rejected requests can be submitted.'))

        if self.state == 'rejected' and self.create_uid != self.env.user:
            raise UserError(_('Only the original requester can resubmit the request.'))

        if self.state == 'rejected':
            self.approval_round += 1
        elif self.state == 'draft':
            # if user reopens from rejected draft, go to next round on submit
            self.approval_round += 1

        if self.state in ['new', 'draft', 'rejected']:
            self.current_approval_level = 0
            self.state = 'waiting_approval'

        self._create_approval_lines()
        self._activate_next_level()
        self._send_approval_notifications()

    def action_set_draft(self):
        self.ensure_one()
        if self.state != 'rejected':
            raise ValidationError(_('Only rejected requests can be set back to draft.'))

        if self.create_uid != self.env.user and not self.env.user.has_group('base.group_system'):
            raise UserError(_('Only the original requester or administrator can reset to draft.'))

        self.state = 'draft'
        self.current_approval_level = 0

    def _create_approval_lines(self):
        """Create approval lines for current request round."""
        existing_round = self.approval_line_ids.filtered(lambda a: a.approval_round == self.approval_round)
        if existing_round:
            return

        for level in range(1, self.max_approval_level + 1):
            approvers = self._get_approver_from_config(level)
            if not approvers:
                continue

            for idx, approver in enumerate(approvers, start=1):
                self.env['asset.request.approval'].create({
                    'request_id': self.id,
                    'approval_level': level,
                    'approver_id': approver.id,
                    'status': 'waiting',
                    'sequence': level * 10 + idx,
                    'approval_round': self.approval_round,
                })

    def _activate_next_level(self):
        next_level = self.current_approval_level + 1
        next_approval = self.approval_line_ids.filtered(
            lambda a: a.approval_level == next_level and a.approval_round == self.approval_round
        )
        if next_approval:
            next_approval.action_set_pending()

    def _get_current_pending_approval(self):
        next_level = self.current_approval_level + 1
        return self.approval_line_ids.filtered(
            lambda a: a.approval_level == next_level and a.status == 'pending' and a.approval_round == self.approval_round
        )

    def _send_approval_notifications(self):
        for request in self:
            pending = request._get_current_pending_approval()
            if pending:
                pending._send_notification()

    def action_approve(self):
        self.ensure_one()

        pending = self._get_current_pending_approval()
        if not pending:
            if self.current_approval_level >= self.max_approval_level:
                raise ValidationError(_('Request sudah fully approved.'))
            else:
                raise ValidationError(_('No pending approval found.'))

        user_pending = pending.filtered(lambda a: a.current_approver_id == self.env.user)
        if not user_pending:
            raise UserError(_('Only the assigned approver can approve this request.'))

        user_pending = user_pending.sorted('sequence')
        for line in user_pending:
            line.action_approve()
            self.message_post(body=_('Approved by %s at level %d') %
                              (line.current_approver_id.name, line.approval_level))

        if pending.filtered(lambda a: a.status == 'pending'):
            return

        next_level = self.current_approval_level + 1
        self.current_approval_level = next_level

        if self.current_approval_level >= self.max_approval_level:
            self.state = 'approved'
            self.message_post(body=_('Asset request fully approved.'))
        else:
            self._activate_next_level()
            self._send_approval_notifications()

    def _reject_pending_approval(self, pending, notes='', attachments=None):
        if not pending or pending.status != 'pending':
            raise ValidationError(_('No pending approval found to reject.'))

        if self.env.user != pending.current_approver_id:
            raise UserError(_('Only %s can reject this level.') % pending.current_approver_id.name)

        if not notes and not attachments:
            raise ValidationError(_('Please provide rejection notes or attachments.'))

        pending.write({
            'status': 'rejected',
            'approval_date': False,
            'reject_date': fields.Datetime.now(),
            'reject_notes': notes,
            'reject_attachment_ids': [(6, 0, attachments.ids)] if attachments else [(6, 0, [])],
        })

        # Cancel other pending approvals in the same level and same round
        same_level = self.approval_line_ids.filtered(
            lambda a: a.approval_level == pending.approval_level and a.approval_round == pending.approval_round and a.status == 'pending' and a != pending
        )
        for line in same_level:
            line.action_cancel()

        higher_approvals = self.approval_line_ids.filtered(
            lambda a: a.approval_level > pending.approval_level and a.approval_round == pending.approval_round and a.status != 'approved'
        )
        for higher in higher_approvals:
            higher.action_cancel()

        self.state = 'rejected'
        self.message_post(body=_('Request rejected by %s at level %d') %
                          (self.env.user.name, pending.approval_level))

    def action_reject(self):
        self.ensure_one()

        pending = self._get_current_pending_approval()
        if not pending:
            raise ValidationError(_('No pending approval found to reject.'))

        user_pending = pending.filtered(lambda a: a.current_approver_id == self.env.user)
        if not user_pending:
            raise UserError(_('Only the assigned approver can reject this request.'))

        pending_line = user_pending.sorted('sequence')[0]

        return {
            'name': _('Reject Approval'),
            'type': 'ir.actions.act_window',
            'res_model': 'asset.request.approval.reject',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.id,
                'default_approval_id': pending_line.id,
            },
        }


    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'asset.request') or _('New')
        return super().create(vals_list)

    @api.constrains('required_date')
    def _check_required_date(self):
        for request in self:
            if request.required_date and request.required_date < fields.Date.today():
                raise ValidationError(
                    _('Required date cannot be in the past.'))

    @api.depends('state')
    def _compute_line_readonly(self):
        for request in self:
            request.line_readonly = request.state in [
                'waiting_approval', 'approved', 'rejected']
            
    def action_send_notification(self):
        """Send notification to all pending approvers"""
        self.ensure_one()
        
        # Cek apakah status waiting_approval
        if self.state != 'waiting_approval':
            raise ValidationError(_('Notifications can only be sent for requests waiting for approval.'))
        
        # Dapatkan semua approval line yang statusnya pending
        pending_approvals = self.approval_line_ids.filtered(lambda a: a.status == 'pending')
        
        if not pending_approvals:
            raise ValidationError(_('No pending approvals found for this request.'))
        
        # Kirim notifikasi ke setiap pending approver
        for approval in pending_approvals:
            approval.write({'notification_sent': False})
            approval._send_notification()
            self.message_post(body=_('Notification sent to %s (Level %d)') % 
                            (approval.current_approver_id.name or approval.approver_id.name, 
                            approval.approval_level))
        
        return True
