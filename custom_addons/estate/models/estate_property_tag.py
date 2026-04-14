from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class PropertyTag(models.Model):
    _name = 'estate.property.tag'
    _description = 'Test Model for Estate Property Tag'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    # color picker for tag
    color = fields.Integer(default=0)
    property_ids = fields.Many2many('estate.property', string='Properties')

    _check_name = models.Constraint(
        'UNIQUE(name)',
        'The tag name should be unique'
    )

    # @api.constrains('name')
    # def _check_unique_name(self):
    #     for rec in self:
    #         if self.search_count([('name', '=', rec.name)]) > 1:
    #             raise ValidationError("The name of the tag must be unique.")
