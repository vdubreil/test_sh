"""
For woo_commerce_ept module.
"""
from odoo import models, fields


class DeliveryCarrier(models.Model):
    """
    Inherited to add the woocommerce carriers.
    @author: Maulik Barad on Date 12-Nov-2019.
    """
    _inherit = "delivery.carrier"
    
    woo_code = fields.Char("Woo Code", help="WooCommerce Delivery Code")
