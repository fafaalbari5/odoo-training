from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from decimal import Decimal, ROUND_HALF_UP


class AssetLeasingAmortization(models.Model):
    _name = 'asset.leasing.amortization'
    _description = 'Asset Leasing Amortization'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: _('New'))
    
    # Relation to Asset Request
    request_id = fields.Many2one(
        'asset.request',
        string='Asset Request',
        required=True,
        ondelete='restrict',
        help='Select the approved asset request'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        related='request_id.partner_id',
        readonly=True,
        store=True,
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    
    # Loan Information
    principal = fields.Monetary(
        string='Principal',
        currency_field='currency_id',
        required=True,
        default=0.0,
    )
    
    annual_rate = fields.Float(
        string='Annual Rate (%)',
        required=True,
        default=7.0,
    )
    
    term_years = fields.Integer(
        string='Term (Years)',
        default=1,
        required=True,
    )
    
    months = fields.Integer(
        string='Number of Months',
        compute='_compute_months',
        store=True,
        readonly=True
    )
    
    monthly_rate = fields.Float(
        string='Monthly Rate',
        compute='_compute_monthly_rate',
        store=True,
        digits=(12, 9),
        readonly=True
    )
    
    start_date = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.context_today
    )
    
    monthly_payment = fields.Monetary(
        string='Monthly Payment',
        currency_field='currency_id',
        compute='_compute_monthly_payment',
        store=True,
        readonly=True
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('computed', 'Computed'),
        ('confirmed', 'Confirmed'),
    ], string='State', default='draft', required=True)
    
    line_ids = fields.One2many(
        'asset.leasing.amortization.line',
        'amortization_id',
        string='Amortization Schedule'
    )

    total_payment = fields.Monetary(string='Total Payment', currency_field='currency_id', compute='_compute_totals', store=False)
    total_interest = fields.Monetary(string='Total Interest', currency_field='currency_id', compute='_compute_totals', store=False)
    total_principal = fields.Monetary(string='Total Principal', currency_field='currency_id', compute='_compute_totals', store=False)

    # ========== ACCOUNTING CONFIGURATION ==========
    vendor_bill_journal_id = fields.Many2one(
        'account.journal',
        string='Vendor Bill Journal',
        domain="[('type', '=', 'purchase')]",
        required=True,
        help='Journal for vendor bills'
    )
    
    interest_expense_account_id = fields.Many2one(
        'account.account',
        string='Interest Expense Account',
        required=True,
        help='Account for recording interest expense'
    )
    
    leasing_payable_account_id = fields.Many2one(
        'account.account',
        string='Leasing Payable Account',
        required=True,
        help='Account for recording leasing payable'
    )
    
    lease_account_payable_id = fields.Many2one(
        'account.account',
        string='Lease Account Payable',
        required=True,
        help='Account for recording lease liability'
    )
    
    # Status vendor bills creation
    vendor_bills_created = fields.Boolean(
        string='Vendor Bills Created',
        default=False,
        readonly=True
    )

    # ========== COMPUTE METHODS ==========
    def _compute_totals(self):
        for rec in self:
            rec.total_payment = sum(line.payment for line in rec.line_ids)
            rec.total_interest = sum(line.interest_amount for line in rec.line_ids)
            rec.total_principal = sum(line.principal_amount for line in rec.line_ids)

    @api.depends('term_years')
    def _compute_months(self):
        for rec in self:
            rec.months = (rec.term_years or 0) * 12

    @api.depends('annual_rate')
    def _compute_monthly_rate(self):
        for rec in self:
            rec.monthly_rate = (rec.annual_rate or 0) / 12.0 / 100.0

    @api.depends('principal', 'months', 'monthly_rate')
    def _compute_monthly_payment(self):
        for rec in self:
            if rec.principal <= 0 or rec.months <= 0:
                rec.monthly_payment = 0.0
                continue
            i = Decimal(rec.monthly_rate)
            n = Decimal(rec.months)
            p = Decimal(rec.principal)
            if i == 0:
                rec.monthly_payment = float((p / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            else:
                z = (1 + i) ** n
                a = i * z
                b = z - 1
                if b == 0:
                    raise ValidationError(_('Invalid amortization formula denominator is zero.'))
                c = a / b
                rec.monthly_payment = float((p * c).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    # ========== ACTION METHODS ==========
    def action_generate_schedule(self):
        """Generate amortization schedule"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise ValidationError(_('Schedule can only be generated from Draft state.'))
        
        if not self.request_id:
            raise ValidationError(_('Please select an asset request first.'))
        
        if self.principal <= 0:
            raise ValidationError(_('Principal must be greater than zero.'))
        if self.months <= 0:
            raise ValidationError(_('Number of months must be greater than zero.'))
        if self.monthly_rate < 0:
            raise ValidationError(_('Monthly rate cannot be negative.'))

        payment_amount = Decimal(self.monthly_payment)
        monthly_rate = Decimal(self.monthly_rate)
        remaining_balance = Decimal(self.principal)

        self.line_ids.unlink()

        for idx in range(1, self.months + 1):
            period_date = self.start_date + relativedelta(months=idx - 1)
            interest_amount = (remaining_balance * monthly_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            principal_amount = (payment_amount - interest_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            if idx == self.months:
                principal_amount = remaining_balance
                payment_amount = (interest_amount + principal_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            remaining_balance = (remaining_balance - principal_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if remaining_balance < 0:
                remaining_balance = Decimal('0.00')

            self.env['asset.leasing.amortization.line'].create({
                'amortization_id': self.id,
                'sequence': idx,
                'date': period_date,
                'payment': float(payment_amount),
                'interest_rate': float(monthly_rate),
                'interest_amount': float(interest_amount),
                'principal_amount': float(principal_amount),
                'remaining_balance': float(remaining_balance),
            })

        self.state = 'computed'
        self.message_post(body=_('Amortization schedule generated successfully.'))

    def action_confirm_schedule(self):
        """Confirm the schedule (finalize)"""
        self.ensure_one()
        
        if self.state != 'computed':
            raise ValidationError(_('Schedule can only be confirmed from Computed state.'))
        
        if not self.line_ids:
            raise ValidationError(_('Please generate schedule first before confirming.'))
        
        self.state = 'confirmed'
        self.message_post(body=_('Amortization schedule confirmed and finalized.'))

    def action_reset(self):
        """Reset to draft and delete schedule"""
        self.ensure_one()
        
        if self.state != 'computed':
            raise ValidationError(_('Only computed schedule can be reset.'))
        
        self.line_ids.unlink()
        self.state = 'draft'
        self.message_post(body=_('Schedule reset to draft.'))

    def action_create_vendor_bills(self):
        """Create vendor bills for all amortization lines"""
        self.ensure_one()
        
        if self.state != 'confirmed':
            raise ValidationError(_('Vendor bills can only be created for confirmed amortization.'))
        
        if self.vendor_bills_created:
            raise ValidationError(_('Vendor bills have already been created for this amortization.'))
        
        if not self.vendor_bill_journal_id:
            raise ValidationError(_('Please configure Vendor Bill Journal first.'))
        
        if not self.interest_expense_account_id or not self.leasing_payable_account_id or not self.lease_account_payable_id:
            raise ValidationError(_('Please configure all accounting accounts first.'))
        
        move_ids = []
        for line in self.line_ids:
            # Create vendor bill dengan 2 invoice lines saja (tanpa credit line)
            move = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'journal_id': self.vendor_bill_journal_id.id,
                'invoice_date': line.date,
                'date': line.date,
                'partner_id': self.partner_id.id,
                'ref': f'Lease Payment - {self.name} - Month {line.sequence}',
                'invoice_line_ids': [
                    (0, 0, {
                        'account_id': self.leasing_payable_account_id.id,
                        'quantity': 1,
                        'price_unit': line.principal_amount,
                        'name': f'Principal Payment - Month {line.sequence}',
                    }),
                    (0, 0, {
                        'account_id': self.interest_expense_account_id.id,
                        'quantity': 1,
                        'price_unit': line.interest_amount,
                        'name': f'Interest Payment - Month {line.sequence}',
                    }),
                ],
            })
            
            move_ids.append(move.id)
            line.journal_entry_id = move.id
        
        self.vendor_bills_created = True
        self.message_post(body=_('Created %d vendor bills.') % len(move_ids))
        
        return {
            'type': 'ir.actions.act_window_close',
            'view_mode': 'form',
            'res_model': 'asset.leasing.amortization',
            'res_id': self.id,
            'target': 'current',
        }

    def action_view_vendor_bills(self):
        """View all vendor bills for this amortization"""
        self.ensure_one()
        
        bills = self.env['account.move'].search([
            ('leasing_amortization_id', '=', self.id)
        ])
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Vendor Bills',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bills.ids)],
            'target': 'current',
        }
    
    def action_edit_accounting_config(self):
        """Edit accounting configuration after confirmation (before creating vendor bills)"""
        self.ensure_one()
        
        if self.vendor_bills_created:
            raise ValidationError(_('Cannot edit accounting configuration after vendor bills have been created.'))
        
        # Set state back to computed to allow editing
        self.state = 'computed'
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit Lease Amortization',
            'res_model': 'asset.leasing.amortization',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq = self.env['ir.sequence'].next_by_code('asset.leasing.amortization') or _('New')
                vals['name'] = seq
        return super().create(vals_list)


class AssetLeasingAmortizationLine(models.Model):
    _name = 'asset.leasing.amortization.line'
    _description = 'Asset Leasing Amortization Line'
    _order = 'amortization_id, sequence'

    amortization_id = fields.Many2one(
        'asset.leasing.amortization',
        string='Amortization',
        required=True,
        ondelete='cascade'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='amortization_id.currency_id',
        readonly=True
    )
    sequence = fields.Integer(string='No.', readonly=True)
    date = fields.Date(string='Payment Date', required=True)
    payment = fields.Monetary(string='Payment', currency_field='currency_id', readonly=True)
    interest_rate = fields.Float(string='Monthly Rate', digits=(12, 9), readonly=True)
    interest_amount = fields.Monetary(string='Interest Amount', currency_field='currency_id', readonly=True)
    principal_amount = fields.Monetary(string='Principal Amount', currency_field='currency_id', readonly=True)
    remaining_balance = fields.Monetary(string='Remaining Balance', currency_field='currency_id', readonly=True)

    journal_entry_id = fields.Many2one(
        'account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
        help='Related vendor bill/journal entry'
    )