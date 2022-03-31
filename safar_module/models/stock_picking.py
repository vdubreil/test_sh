# -*- coding: utf-8 -*-
from odoo import fields, models, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sh_mrp_ids = fields.Many2many(
        comodel_name='mrp.production',
        string="Ordre de fabrication",
        compute='_compute_mrp_orders'
    )

    @api.model
    def create(self, values):
        record = super(StockPicking, self).create(values)

        if record.picking_type_id.id == 2: # uniquement si livraison client
            # on ajoute par défaut le transporteur GLS au BL
            company = self.env['res.company'].search([('id', '=', record.company_id.id)])
            if company:
                if company.s_methode_expe_par_defaut:
                    record.carrier_id = company.s_methode_expe_par_defaut.id

        return record

    def _compute_mrp_orders(self):
        if self:
            for rec in self:
                mrp_orders = self.env['mrp.production'].sudo().search([
                    ('origin', '=', rec.origin)
                ])
                if mrp_orders:
                    rec.sh_mrp_ids = [(6, 0, mrp_orders.ids)]
                else:
                    rec.sh_mrp_ids = False

    def button_etiq_livraison(self):
        return self.env.ref('safar_module.action_report_label_livraison').report_action(self)

    def write(self, values):
        record = super(StockPicking, self).write(values)
        if record:
            if self.state == 'done':
                for of in self.sh_mrp_ids:
                    of.s_id_box = False

        return record
