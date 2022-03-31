"""
For woo_commerce_ept module.
"""
import logging

from odoo import models, fields

_logger = logging.getLogger("Woo")


class WooProductImageEpt(models.Model):
    """
    For attaching images with woo and odoo products.
    @author: Maulik Barad on Date 10-Dec-2019.
    """
    _name = "woo.product.image.ept"
    _description = "Woo Product Image"
    _order = "sequence, id"

    odoo_image_id = fields.Many2one("common.product.image.ept", ondelete="cascade")
    woo_image_id = fields.Char(help="Id of image in Woo.",size=100)
    woo_variant_id = fields.Many2one("woo.product.product.ept")
    woo_template_id = fields.Many2one("woo.product.template.ept")
    url = fields.Char(related="odoo_image_id.url", help="External URL of image")
    image = fields.Image(related="odoo_image_id.image")
    sequence = fields.Integer(help="Sequence of images.", index=True, default=10)
    image_mime_type = fields.Char(help="This field is used to set image mine type.")