from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class AssetRequestCron(models.Model):
    _name = 'asset.request.cron'
    _description = 'Asset Request Cron Jobs'
    _transient = True  # Tambahkan ini agar tidak membuat tabel di database
    
    @api.model
    def send_approval_reminders(self):
        """Send reminder notifications for pending approvals (called by cron job)"""
        _logger.info('Starting approval reminder cron job...')
        
        # Get all pending approvals
        pending_approvals = self.env['asset.request.approval'].search([
            ('status', '=', 'pending')
        ])
        
        reminder_count = 0
        for approval in pending_approvals:
            # Send reminder
            approval._send_reminder()
            reminder_count += 1
        
        _logger.info('Approval reminder cron job completed. Sent %d reminders.', reminder_count)
        return True