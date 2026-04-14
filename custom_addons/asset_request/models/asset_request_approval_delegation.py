from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AssetRequestApprovalDelegation(models.Model):
    _name = 'asset.request.approval.delegation'
    _description = 'Asset Request Approval Delegation'

    approver_id = fields.Many2one('res.users', string='Approver', required=True)
    delegator_id = fields.Many2one('res.users', string='Delegator', default=lambda self: self.env.user, readonly=True)
    delegate_to_id = fields.Many2one('res.users', string='Delegate To', required=True)
    date_from = fields.Date(string='Delegate From', required=True, default=fields.Date.context_today)
    date_to = fields.Date(string='Delegate Until', required=True)
    notes = fields.Text(string='Delegate Notes')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired')
    ], string='State', default='active', readonly=True)

    is_active = fields.Boolean(string='Active Delegation', compute='_compute_is_active', store=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise UserError(_('Delegate To date must be after Delegate From date.'))

    @api.depends('date_from', 'date_to', 'state')
    def _compute_is_active(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_active = rec.state == 'active' and rec.date_from <= today <= rec.date_to

    def action_activate(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.state = 'active'

    def action_expire(self):
        for rec in self:
            rec.state = 'expired'

    def action_confirm_delegate(self):
        for rec in self:
            if self.env.user != rec.approver_id and not self.env.user.has_group('base.group_system'):
                raise UserError(_('Only the approver (or admin) can confirm this delegation.'))
            if rec.date_to < fields.Date.context_today(self):
                raise UserError(_('Delegate period has already expired.'))
            rec.state = 'active'
            rec.message_post(
                body=_('Approval delegated from %s to %s between %s and %s') % (
                    rec.approver_id.name,
                    rec.delegate_to_id.name,
                    rec.date_from,
                    rec.date_to,
                )
            )
