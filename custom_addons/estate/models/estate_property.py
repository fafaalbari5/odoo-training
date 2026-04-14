from odoo import models, fields, api
from datetime import timedelta
from odoo.exceptions import UserError, ValidationError

class RealEstate(models.Model):
    _name = 'estate.property'
    _description = 'Test Model for Estate Property'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # _sql_constraints = [
    #     ("check_expected_price", "CHECK(expected_price > 0)", "Expected price cannot be negative."),
    #     ("check_selling_price", "CHECK(selling_price >= 0)", "Selling price cannot be negative."),
    # ]
    _order = 'id desc'

    active = fields.Boolean(default=True)
    name = fields.Char(string='Name', required=True, tracking=True)
    state = fields.Selection(
        [
            ('new', 'New'),
            ('received', 'Offer Received'),
            ('accepted', 'Offer Accepted'),
            ('sold', 'Sold'),
            ('canceled', 'Canceled'),
        ],
        required=True, copy=False, default='new', tracking=True
    )
    postcode = fields.Char(string='Postcode')
    currency_id = fields.Many2one('res.currency', string='Currency')
    price = fields.Float('Price', tracking=True)

    def _default_date(self):
        # set availability is in 3 months
        return fields.Date.today() + timedelta(days=90)

    date_availability = fields.Date(string='Date Availability', default=_default_date , copy=False, tracking=True)
    expected_price = fields.Float('Expected Price', tracking=True)
    selling_price = fields.Float('Selling Price' , readonly=True , copy=False, tracking=True)

    description = fields.Text(string='Description')
    bedrooms = fields.Integer(string='Bedrooms' , default=2, tracking=True)
    living_area = fields.Integer(string='Living Area (sqm)', tracking=True)
    facades = fields.Integer(string='Facades')
    garage = fields.Boolean(string='Garage')
    garden = fields.Boolean(string='Garden')
    garden_area = fields.Integer(string='Garden Area (sqm)')
    total_area = fields.Integer(string='Total Area (sqm)', compute='_compute_total_area')

    @api.depends('living_area', 'garden_area')
    def _compute_total_area(self):
        for record in self:
            record.total_area = sum([record.living_area, record.garden_area])

    garden_orientation = fields.Selection(
        [
            ('north', 'North'),
            ('south', 'South'),
            ('east', 'East'),
            ('west', 'West'),
        ],
        string='Garden Orientation'
    )
    property_type_id = fields.Many2one('estate.property.type', string='Property Type', tracking=True)

    buyer_id = fields.Many2one('res.partner', string='Buyer', copy=False, tracking=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user, copy=False, tracking=True)

    offer_ids = fields.One2many('estate.property.offer', 'property_id', string='Offers')

    tag_ids = fields.Many2many('estate.property.tag', string='Tags')

    best_offer = fields.Float(compute='_compute_best_offer', string='Best Offer')
    
    
    _check_expected_price = models.Constraint(
        'CHECK(expected_price > 0)', 'Expected price cannot be negative.'
    )
    _check_selling_price = models.Constraint(
        'CHECK(selling_price >= 0)', 'Selling price cannot be negative.'
    )
    
    @api.depends('offer_ids.price')
    def _compute_best_offer(self):
        for property in self:
            property.best_offer = max(property.offer_ids.mapped('price')) if property.offer_ids else 0

    @api.onchange('garden')
    def _onchange_garden(self):
        for estate in self:
            if estate.garden:
                if not estate.garden_area:
                    estate.garden_area = 10
                if not estate.garden_orientation:
                    estate.garden_orientation = 'north'
            else:
                # Jika garden tidak dicentang, reset semua field garden
                estate.garden_area = 0
                estate.garden_orientation = False
    
    @api.onchange('date_availability')
    def _onchange_date_availability(self):
        for estate in self:
            if estate.date_availability and estate.date_availability < fields.Date.today():
                return {
                    'warning': {
                        'title': "WARNING!! Invalid Date",
                        'message': "The date availability must be in the future",
                    },
                }
            
    def action_sold(self):
        for estate in self:
            if estate.state == 'canceled':
                raise UserError("You cannot sell a canceled property.")
            
            accepted_offers = estate.offer_ids.filtered(lambda o: o.status == 'accepted')
            if not accepted_offers:
                raise UserError("You cannot sell a property without an accepted offer.")
            
            if estate.selling_price <= 0:
                raise UserError("Selling price must be set before selling the property.")
            
            estate.state = 'sold'

    def action_cancel(self):
        for estate in self:
            if estate.state == 'sold':
                raise UserError("You cannot cancel a sold property.")
            estate.state = 'canceled'

    @api.constrains('selling_price')
    def _check_selling_price(self):
        for record in self:
            if record.selling_price < 0:
                raise ValidationError("Selling price cannot be negative.")
            
    @api.constrains('expected_price')
    def _check_expected_price(self):
        for record in self:
            if record.expected_price < 0:
                raise ValidationError("Expected price cannot be negative.")
            
    @api.constrains('selling_price', 'expected_price')
    def _check_selling_price_vs_expected(self):
        for record in self:
            if record.selling_price == 0:
                continue  # Skip check if selling price is not set
            min_acceptable_price = record.expected_price * 0.9
            if record.selling_price < min_acceptable_price:
                raise ValidationError("Selling price cannot be less than 90% of the expected price.")

    @api.ondelete(at_uninstall=False)
    def _unlink_except_new_or_canceled(self):
        for record in self:
            if record.state not in ['new', 'canceled']:
                raise UserError("You can only delete properties that are in 'new' or 'canceled' state.")
            

    @api.ondelete(at_uninstall=False)
    def _unlink_property(self):
        for record in self:
            if record.offer_ids:
                raise UserError("Cannot delete property with existing offers. Delete offers first.")

    