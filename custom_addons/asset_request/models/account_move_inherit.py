from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Relasi ke leasing amortization
    leasing_amortization_id = fields.Many2one(
        'asset.leasing.amortization',
        string='Leasing Amortization',
        readonly=True,
        copy=False,
        help='Reference to the leasing amortization document',
        ondelete='set null'
    )
    
    leasing_line_id = fields.Many2one(
        'asset.leasing.amortization.line',
        string='Amortization Line',
        readonly=True,
        copy=False,
        help='Reference to the specific amortization line',
        ondelete='set null'
    )
    
    is_leasing_bill = fields.Boolean(
        string='Is Leasing Bill',
        compute='_compute_is_leasing_bill',
        store=False
    )
    
    @api.depends('leasing_amortization_id')
    def _compute_is_leasing_bill(self):
        for move in self:
            move.is_leasing_bill = bool(move.leasing_amortization_id)
    
    # def action_post(self):
    #     """Override post to handle auto post tracking"""
    #     result = super().action_post()
        
    #     for move in self:
    #         if move.is_leasing_bill and move.auto_post != 'no':
    #             move.last_posted_date = fields.Date.today()
                
    #             # Cek apakah masih dalam batas Auto Post Until
    #             if move.auto_post_until and fields.Date.today() >= move.auto_post_until:
    #                 move.auto_post = 'no'
    #                 continue
                
    #             # Update next post date jika masih ada schedule berikutnya
    #             if move.leasing_line_id:
    #                 next_line = self.env['asset.leasing.amortization.line'].search([
    #                     ('amortization_id', '=', move.leasing_amortization_id.id),
    #                     ('sequence', '>', move.leasing_line_id.sequence)
    #                 ], limit=1)
                    
    #                 if next_line:
    #                     move.leasing_line_id = next_line
    #                     move.date = next_line.date
    #                     move._update_move_lines()
    #                     move.state = 'draft'
    #                     move.name = False
    #                 else:
    #                     move.auto_post = 'no'
                        
    #     return result
    
    # def _update_move_lines(self):
    #     """Update move lines when moving to next period"""
    #     for move in self:
    #         if not move.leasing_line_id:
    #             continue
            
    #         line = move.leasing_line_id
            
    #         # Clear existing lines
    #         move.line_ids.unlink()
            
    #         # Create new lines
    #         self.env['account.move.line'].create([
    #             {
    #                 'move_id': move.id,
    #                 'account_id': move.leasing_amortization_id.leasing_payable_account_id.id,
    #                 'debit': line.principal_amount,
    #                 'credit': 0.0,
    #                 'name': f'Principal Payment - Month {line.sequence}',
    #             },
    #             {
    #                 'move_id': move.id,
    #                 'account_id': move.leasing_amortization_id.interest_expense_account_id.id,
    #                 'debit': line.interest_amount,
    #                 'credit': 0.0,
    #                 'name': f'Interest Payment - Month {line.sequence}',
    #             },
    #             {
    #                 'move_id': move.id,
    #                 'account_id': move.leasing_amortization_id.lease_account_payable_id.id,
    #                 'debit': 0.0,
    #                 'credit': line.payment,
    #                 'name': f'Total Payment - Month {line.sequence}',
    #             },
    #         ])
            
    #         move.amount_total = line.payment

    # @api.model
    # def _cron_auto_post_vendor_bills(self):
    #     """Auto post vendor bills based on schedule"""
    #     today = fields.Date.today()
    #     _logger.info('Starting auto post vendor bills cron job...')
        
    #     # Gunakan field bawaan Odoo: auto_post dan auto_post_until
    #     bills = self.search([
    #         ('state', '=', 'draft'),
    #         ('auto_post', '!=', 'no'),
    #         ('leasing_amortization_id', '!=', False),
    #         ('auto_post_until', '<=', today)
    #     ])
        
    #     posted_count = 0
    #     for bill in bills:
    #         try:
    #             bill.action_post()
    #             posted_count += 1
    #             _logger.info('Auto posted bill %s for leasing %s', 
    #                         bill.name, bill.leasing_amortization_id.name)
    #         except Exception as e:
    #             _logger.error('Failed to auto post bill %s: %s', bill.id, str(e))
        
    #     _logger.info('Auto post cron completed. Posted %d bills.', posted_count)
    #     return True


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    leasing_amortization_id = fields.Many2one(
        'asset.leasing.amortization',
        string='Leasing Amortization',
        related='move_id.leasing_amortization_id',
        store=False
    )