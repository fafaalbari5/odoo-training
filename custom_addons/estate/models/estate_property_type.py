from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class PropertyType(models.Model):
    _name = 'estate.property.type'
    _description = 'Test Model for Estate Property Type'
    # _sql_constraints = [
    #     ("unique_estate_property_type_name_pasti", "UNIQUE (name)", "The name must be unique."),
    # ]
    _order = 'sequence desc'

    sequence = fields.Integer(default=1)
    name = fields.Char(string='Name', required=True)
    property_ids = fields.One2many('estate.property', 'property_type_id', string='Properties')
    property_count = fields.Integer(string='Property Count', compute='_compute_property_count')

    _check_name = models.Constraint(
        'UNIQUE(name)',
        'The type name should be unique'
    )

    # @api.model
    # def create(self, vals_list):
    #     res = super().create(vals_list)
    #     for vals in vals_list:
    #         self.env['estate.property.type'].create(
    #             {
    #                 'name': vals.get('name'),
    #             }
    #         )
    #     return res
    
    def unlink(self):
        if self.property_ids:
            self.property_ids.write({'state': 'canceled'})
        return super().unlink()

    @api.depends('property_ids')
    def _compute_property_count(self):
        for record in self:
            record.property_count = len(record.property_ids)
    
    def action_open_property_id(self):
        return {
            'name': 'Properties',
            'type': 'ir.actions.act_window',
            'res_model': 'estate.property',
            'view_mode': 'list,form',
            'target': 'current',
            'domain': [('property_type_id', '=', self.id)],
            'context': {'default_property_type_id': self.id}
        }

    # @api.constrains('name')
    # def _check_unique_name(self):
    #     for rec in self:
    #         if self.search_count([('name', '=', rec.name)]) > 1:
    #             raise ValidationError("The name of the property type must be unique.")
