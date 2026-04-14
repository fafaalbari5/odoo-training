from odoo import models, fields, api
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError, ValidationError

class EstateOffer(models.Model):
    _name = 'estate.property.offer'
    _description = 'Test Model for Estate Property Offer'
    # _sql_constraints = [
    #     ("check_offer_price", "CHECK(price > 0)", "The Offer Price cannot be negative."),
    # ]
    _order = 'price desc'

    price = fields.Float(string='Price')
    status = fields.Selection([
        ('accepted', 'Accepted'),
        ('refused', 'Refused'),
    ], string='Status' , copy=False)
    partner_id = fields.Many2one('res.partner', string='Partner' , required=True)
    property_id = fields.Many2one('estate.property', string='Property' , required=True)

    property_type_id = fields.Many2one(related='property_id.property_type_id', string='Property Type', store=True)
    validity = fields.Integer(string='Validity (days)', default=7)
    date_deadline = fields.Date(string='Deadline', compute='_compute_date_deadline', inverse='_inverse_date_deadline', store=True)

    _check_name = models.Constraint(
        "CHECK(price > 0)", "The Offer Price cannot be negative."
    )

    @api.depends('create_date', 'validity')
    def _compute_date_deadline(self):
        for offer in self:
            if offer.create_date:
                create_date = fields.Datetime.from_string(offer.create_date).date()
            else:
                create_date = fields.Date.today()
            offer.date_deadline = create_date + relativedelta(days=offer.validity)

    def _inverse_date_deadline(self):
        for offer in self:  # Lebih baik pakai 'offer' daripada 'property' karena ini di model offer
            if offer.date_deadline and offer.create_date:
                create_date = fields.Datetime.from_string(offer.create_date).date()
                offer.validity = (offer.date_deadline - create_date).days
            else:
                offer.validity = 0

    def action_accept(self):
        self.ensure_one()
        if "accepted" in self.property_id.offer_ids.mapped('status'):
            raise UserError("An offer has already been accepted for this property.")
        self.status = 'accepted'
        self.property_id.selling_price = self.price
        self.property_id.state = 'accepted'

    def action_refuse(self):
        self.ensure_one()
        if self.status == 'accepted':
            raise UserError("You cannot refuse an offer that has already been accepted.")
        self.status = 'refused'

    # @api.constrains('price')
    # def _check_offer_price(self):
    #     for offer in self:
    #         if offer.price <= 0:
    #             raise ValidationError("The Offer Price cannot be negative.")
            
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            property_id = vals.get('property_id')
            if property_id:
                property_record = self.env['estate.property'].browse(property_id)

                existing_offers = property_record.offer_ids.mapped('price')

                if existing_offers and vals.get('price', 0) < max(existing_offers):
                    raise ValidationError(
                        f"Offer price must be higher than the highest existing offer: {max(existing_offers)}"
                    )

                property_record.state = 'received'

        return super().create(vals_list)
            
    

