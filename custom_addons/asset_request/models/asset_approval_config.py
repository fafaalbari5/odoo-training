from odoo import models, fields, api, _
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AssetApprovalConfig(models.Model):
    _name = 'asset.approval.config'
    _description = 'Asset Approval Configuration'
    _rec_name = 'name'

    name = fields.Char(
        string='Configuration Name',
        required=True,
        default='Default Approval Matrix'
    )
    # active = fields.Boolean(default=True)

    # Approver per level (single legacy fields)
    level_1_user_id = fields.Many2one('res.users', string='Level 1 (Manager)')
    level_2_user_id = fields.Many2one('res.users', string='Level 2 (Sr. Manager)')
    level_3_user_id = fields.Many2one('res.users', string='Level 3 (Director)')

    # Approvers per level (multiple, preferred)
    level_1_user_ids = fields.Many2many(
        'res.users',
        'asset_approval_config_level1_rel',
        'config_id',
        'user_id',
        string='Level 1 Approvers'
    )
    level_2_user_ids = fields.Many2many(
        'res.users',
        'asset_approval_config_level2_rel',
        'config_id',
        'user_id',
        string='Level 2 Approvers'
    )
    level_3_user_ids = fields.Many2many(
        'res.users',
        'asset_approval_config_level3_rel',
        'config_id',
        'user_id',
        string='Level 3 Approvers'
    )

    # Aturan Dinamis
    rule_ids = fields.One2many('asset.approval.rule', 'config_id', string='Approval Rules')

    @api.model
    def _get_active_config(self):
        """Get active configuration, create default if none exists"""
        config = self.search([], limit=1)
        if not config:
            config = self._create_default_config()
        return config
    
    @api.model
    def _create_default_config(self):
        """Create default configuration (fallback if no XML data exists)"""
        admin = self.env.ref('base.user_admin')
        config =  self.create({
            'name': 'Default Approval Matrix',
            'level_1_user_id': admin.id,
            'level_2_user_id': admin.id,
            'level_3_user_id': admin.id,
            'level_1_user_ids': [(6, 0, [admin.id])],
            'level_2_user_ids': [(6, 0, [admin.id])],
            'level_3_user_ids': [(6, 0, [admin.id])],
            # 'active': True,
        })

        # Create default rules
        self.env['asset.approval.rule']._create_default_rules(config.id)

        return config
    
    @api.model_create_multi
    def create(self, vals_list):
        """Prevent creating multiple configurations"""
        if self.search_count([]) > 0:
            raise UserError(_('Only one approval configuration is allowed. You can edit the existing one.'))
        return super().create(vals_list)

    def unlink(self):
        """Prevent deleting the configuration"""
        raise UserError(_('You cannot delete the approval configuration. You can only edit it.'))

    def copy(self, default=None):
        raise UserError(_('You cannot duplicate the approval configuration.'))


class AssetApprovalRule(models.Model):
    _name = 'asset.approval.rule'
    _description = 'Asset Approval Rule'
    _order = 'sequence asc, min_quantity desc'  # Urutkan berdasarkan sequence, lalu quantity tertinggi dulu

    config_id = fields.Many2one('asset.approval.config', string='Configuration', ondelete='cascade')
    brand_ids = fields.Many2many('fleet.vehicle.model.brand', string='Brands', help="Leave empty to apply to all brands")
    min_quantity = fields.Integer(string='If Quantity Greater Than', default=0, help="Rule applies when quantity > this value")
    required_level = fields.Selection([
        ('1', 'Level 1 Only'),
        ('2', 'Up to Level 2'),
        ('3', 'Up to Level 3')
    ], string='Required Level', required=True)
    sequence = fields.Integer(string='Sequence', default=10, help="Lower number evaluated first")
    
    @api.model
    def _create_default_rules(self, config_id):
        """Create default approval rules based on Excel with correct order"""
        # Get brand IDs
        honda = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Honda')], limit=1)
        toyota = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Toyota')], limit=1)
        mitsubishi = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Mitsubishi')], limit=1)
        mazda = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Mazda')], limit=1)
        bmw = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'BMW')], limit=1)
        mercedes = self.env['fleet.vehicle.model.brand'].search([('name', '=', 'Mercedes')], limit=1)
        
        # ========== URUTAN PENTING: Rule yang lebih spesifik (quantity besar) harus dievaluasi lebih dulu ==========
        
        # Rule 1: Quantity > 2 untuk semua brand -> Level 3 (PALING SPESIFIK, harus pertama)
        self.create({
            'config_id': config_id,
            'brand_ids': [(6, 0, [])],  # Empty means all brands
            'min_quantity': 2,
            'required_level': '3',
            'sequence': 10, 
        })
        
        # Rule 2: European brands (BMW, Mercedes) with quantity > 0 (all) -> Level 2
        european_brands = [b.id for b in [bmw, mercedes] if b]
        if european_brands:
            self.create({
                'config_id': config_id,
                'brand_ids': [(6, 0, european_brands)],
                'min_quantity': 0,
                'required_level': '2',
                'sequence': 20, 
            })
        
        # Rule 3: Japanese brands with quantity > 0 (all) -> Level 1
        japanese_brands = [b.id for b in [honda, toyota, mitsubishi, mazda] if b]
        if japanese_brands:
            self.create({
                'config_id': config_id,
                'brand_ids': [(6, 0, japanese_brands)],
                'min_quantity': 0,
                'required_level': '1',
                'sequence': 30, 
            })