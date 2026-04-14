from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AssetRequestLine(models.Model):
    _name = 'asset.request.line'
    _description = 'Asset Request Line'

    request_id = fields.Many2one(
        'asset.request',
        string='Request',
        required=True,
        ondelete='cascade'
    )
    
    product_brand_id = fields.Many2one(
        'fleet.vehicle.model.brand',
        string='Product Brand',
        required=True,
        domain=[('name', 'in', ['Honda', 'Toyota', 'Mitsubishi', 'Mazda', 'BMW', 'Mercedes'])]
    )
    
    product_model_id = fields.Many2one(
        'fleet.vehicle.model',
        string='Product Model',
        required=True,
        domain="[('brand_id', '=', product_brand_id)]"
    )
    
    product_brand = fields.Char(
        string='Brand Name',
        related='product_brand_id.name',
        store=True
    )
    
    product_model = fields.Char(
        string='Model Name',
        related='product_model_id.name',
        store=True
    )
    
    quantity = fields.Integer(
        string='Quantity',
        required=True,
        default=1
    )
    
    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError('Quantity must be greater than 0.')