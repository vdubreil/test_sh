# -*- coding: utf-8 -*-
from odoo import fields, models, api


class AccountMove(models.Model):
    _inherit = 'account.move'

    s_dthr_export_importateur = fields.Datetime(copy=False)
    s_dt_export_importateur = fields.Date(copy=False)
    s_dt_export_sage = fields.Date(copy=False)
    s_num_client_facture_related = fields.Integer(related="partner_id.s_num_client", string="Cd Client", store="false")
    s_compte_sage_related = fields.Char(related="partner_id.s_compte_sage", string="Compte Tiers")
    # on surcharge le champ existant invoice_user_id pour éviter qu'il ne prenne par défaut l'utilisateur en cours
    # sinon, on le retrouve en tant qu'expé dans le mail d'envoi de la facture au lieu de celui qui a facturé
    # invoice_user_id = fields.Many2one(default="")

    # Parmi les champs que l'on veut alimenter dans la ligne de facture, l'un comportait au début une fonction compute
    # Lorsqu'on crée une facture issue d'une cde, pas de problème, on ramène bien les valeurs dans les nouveaux champs
    # Par contre, pour une facture manuelle, comme il n'y a pas de ligne de cde associée, cela mettait tous les champs
    # à blanc alors qu'on les avaient renseignés manuellement
    # Du coup, on passe par une surcharge des fonctions create et write que l'on distingue selon que c'est une facture
    # manuelle ou issue d'une cde
    @api.model
    def create(self, vals):
        # on positionne l'utilisateur en cours comme vendeur dans la facture pour toujours avoir en expéditeur,
        # l'utilisateur qui crée la facture(Mantis 1192)
        context = self._context
        if context:
            current_uid = context.get('uid')
            if current_uid:
                vals["invoice_user_id"] = current_uid
                vals["user_id"] = current_uid  # on force aussi ce champ pour éviter que le vendeur (issu de la cde) ne soit ajouté comme follower

        if vals.get("invoice_origin"):
            return self.create_from_so(vals)
        else:
            return self.create_manual(vals)

    # @api.model
    def write(self, vals):
        if not vals.get("invoice_origin"):
            return self.write_manual(vals)

    """Appelé lors de la création d'une facture depuis une sale order"""
    def create_from_so(self, vals):
        res = super().create(vals)
        for rec in res:
            for line in rec.invoice_line_ids:
                id_cde = 0
                nm_cde = ''
                dt_cde = ''
                id_line_cde = 0
                ref_order_clt = ''
                num_line = ''
                cd_concession = ''
                prdt_id = 0
                ref_client = ''
                for ref in line.sale_line_ids:  # = sale.order.line
                    id_cde = ref.order_id
                    nm_cde = ref.order_id.name
                    dt_cde = ref.order_id.date_order
                    id_line_cde = ref.id
                    num_line = ref.s_no_ligne_commande
                    ref_order_clt = ref.order_id.client_order_ref
                    cd_concession = ref.order_id.s_code_concession_related
                    prdt_id = ref.product_id
                    ref_client = ref.s_ref_client if ref.product_id == prdt_id else ''

                self.env["account.move.line"].search([("id", "=",line.id)]).write({
                    's_cde_id': id_cde,
                    's_cde_name': nm_cde,
                    's_cde_date': dt_cde,
                    's_cde_line_id': id_line_cde,
                    's_no_ligne_commande': num_line,
                    's_ref_order_client': ref_order_clt,
                    's_code_concession': cd_concession,
                    's_ref_client': ref_client
                })

        return res

    """Appelé lors de la création d'une facture manuelle (donc hors sale order)"""
    def create_manual(self, vals):
        line_ids = self.fix_create(vals)
        if line_ids:
            vals["line_ids"] = line_ids

        return super().create(vals)

    """Appelé lors de la modification d'une facture manuelle (donc hors sale order)"""
    def write_manual(self, vals):
        line_ids = self.fix_write(vals)
        if line_ids:
            vals["line_ids"] = line_ids

        return super().write(vals)

    def fix_create(self, vals):
        invoice_line_ids = vals.get("invoice_line_ids")
        line_ids = vals.get("line_ids")
        if invoice_line_ids and line_ids:
            for invoice_line_id in invoice_line_ids:
                matching_line = self.get_matching_line(invoice_line_id,line_ids)
                if matching_line:
                    matching_line[2]["s_ref_client"] = invoice_line_id[2]["s_ref_client"]
                    matching_line[2]["s_no_ligne_commande"] = invoice_line_id[2]["s_no_ligne_commande"]
                    matching_line[2]["s_ref_order_client"] = invoice_line_id[2]["s_ref_order_client"]
                    matching_line[2]["s_code_concession"] = invoice_line_id[2]["s_code_concession"]
            return line_ids
        else:
            return False

    def fix_write(self, vals):
        invoice_line_ids = vals.get("invoice_line_ids")
        line_ids = vals.get("line_ids")
        if line_ids and invoice_line_ids:
            for invoice_line_id in invoice_line_ids:
                matching_line = self.get_matching_line(invoice_line_id, line_ids)
                if matching_line and invoice_line_id[2]:
                    for key in invoice_line_id[2].keys():
                        if key[:2] == 's_':
                            matching_line[2][key] = invoice_line_id[2].get(key)
            return line_ids
        else:
            return False

    def get_matching_line(self, invoice_line, line_ids):
        if line_ids:
            for line in line_ids:
                if line[1] == invoice_line[1]:
                    return line
        return False


    """Appliquer les remises de l'importateur"""
    @api.depends('invoice_line_ids', 'sale_line_ids', 'order_id.pricelist_id.item_ids', 'product_template_id', 'quantity', 'discount', 'price_unit', 'tax_ids')
    def call_chercher_remise_importateur(self):
        for record in self:
            for fac_line in record.with_context(check_move_validity=False).invoice_line_ids:
                remise = fac_line.discount
                for order_line in fac_line.sale_line_ids:
                    for price_item in order_line.order_id.pricelist_id.item_ids.sorted(key=lambda x: x.min_quantity, reverse=True):
                        if price_item.product_id and price_item.product_id == order_line.product_id and \
                                price_item.product_tmpl_id == order_line.product_id.product_tmpl_id \
                                and fac_line.quantity >= price_item.min_quantity:
                            remise = price_item.s_tx_remise_facturation
                            break
                        else:
                            if price_item.product_tmpl_id == order_line.product_template_id and \
                                    not price_item.product_id \
                                    and fac_line.quantity >= price_item.min_quantity:
                                remise = price_item.s_tx_remise_facturation
                                break

                fac_line.discount = remise

        self.with_context(check_move_validity=False)._recompute_dynamic_lines(recompute_all_taxes = True, recompute_tax_base_amount = True)


    """Ouvre le site d'export des factures d'importateur"""
    def call_safar_export_facture_importateur(self):
        url_site = self.env['ir.config_parameter'].get_param('url.export_facture_importateur')
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': url_site + '?invoice_ids=' + str(self.id),
        }

    """Ouvre le site d'export des factures d'importateur pour les factures
    sélectionnées"""

    def call_safar_export_selected_factures_importateur(self):
        url_site = self.env['ir.config_parameter'].get_param('url.export_facture_importateur')
        invoice_list = ""
        for record in self:
            invoice_list += str(record.id) if invoice_list == "" else ';' + str(record.id)
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': url_site + '?invoice_ids=' + invoice_list,
        }

    def calcul_ca_facture(self):
        if self:
            if self.state in ('posted'):
                record.calcul_ca_facture_an()
                record.calcul_ca_facture_clt()
                record.calcul_ca_facture_art()

    # Calculer les CA facturés par an
    def calcul_ca_facture_an(self, idclt=False):
        # paramètre client
        param_clt1 = ""
        param_clt2 = ""
        if idclt:
            param_clt1 = " and fac.partner_id = " + str(idclt)
            param_clt2 = " WHERE s_partner_id = " + str(idclt)

        # on vide la table
        self.env.cr.execute('DELETE FROM s_partner_inv_an' + str(param_clt2))

        # on récupère les aggrégats par une rqte
        self.env.cr.execute("""
            INSERT INTO s_partner_inv_an(s_partner_id, currency_id, s_year, s_ca_avt_remise, s_remise_importateur, s_ca_apr_remise)
            SELECT fac.partner_id, fal.currency_id, to_char(fac.invoice_date,'YYYY') AS year, 
                sum(fal.quantity*fal.price_unit),
                sum(fal.price_subtotal - (fal.quantity*fal.price_unit)), 
                sum(fal.price_subtotal)
            FROM account_move as fac
            INNER JOIN account_move_line AS fal ON fac.id = fal.move_id
            WHERE fac.state IN ('posted') AND fal.exclude_from_invoice_tab='f' """ + param_clt1 + """
            GROUP BY fac.partner_id, fal.currency_id, to_char(fac.invoice_date,'YYYY')
        """)

    # Calculer les CA facturés par client livré
    def calcul_ca_facture_clt(self, idclt=False):
        # paramètre du nb de jours glissants pour déterminer la période par défaut
        nb_jr_glissant = self.env['ir.config_parameter'].get_param('nb.jr.glissant.palmares')
        if not nb_jr_glissant:
            nb_jr_glissant = 365
        nb_jr_glissant = int(nb_jr_glissant) - 1  # on enlève un jour car le jour en cours est pris en compte

        # paramètre client
        param_clt1 = ""
        param_clt2 = ""
        if idclt:  # appel depuis bouton recalculer de la fiche client
            param_clt1 = " and fac.partner_id = " + str(idclt)
            param_clt2 = " WHERE s_partner_id = " + str(idclt)
        else:
            # on est sur tous les clients donc en traitement de nuit, donc on remet tous les clients sur une année glissante
            self.env.cr.execute(
                "UPDATE res_partner SET s_period_from = NOW() - INTERVAL '" + str(nb_jr_glissant) + " DAY' ")
            self.env.cr.execute("UPDATE res_partner SET s_period_to = NOW() ")

        # on vide la table des données de tous les clients ou du client passé en paramètre
        self.env.cr.execute("DELETE FROM s_partner_inv_clt " + str(param_clt2))

        # on passe une rqte pour calculer le palmarès de tous les clients ou du client passé en paramètre
        self.env.cr.execute("""
            INSERT INTO s_partner_inv_clt(s_partner_id,s_partner_id_cde,currency_id,s_ca_avt_remise,s_remise_importateur,s_ca_apr_remise)
            SELECT fac.partner_id, fal.s_init_client, fal.currency_id, 
                sum(fal.quantity*fal.price_unit) AS ca_avt_remise,
                sum(fal.price_subtotal - (fal.quantity*fal.price_unit)) AS remise, 
                sum(fal.price_subtotal) AS ca_apr_remise
            FROM account_move as fac
            INNER JOIN account_move_line AS fal ON fac.id = fal.move_id
            INNER JOIN res_partner AS pa ON fac.partner_id = pa.id
            WHERE fac.state IN ('posted') AND fal.exclude_from_invoice_tab='f' 
            AND DATE(fac.invoice_date) >= COALESCE(pa.s_period_from, NOW() - INTERVAL '""" + str(nb_jr_glissant) + """ DAY') AND DATE(fac.invoice_date) <= COALESCE(pa.s_period_to,NOW())
            """ + param_clt1 + """
            GROUP BY fac.partner_id, fal.s_init_client, fal.currency_id
            ORDER BY sum(fal.price_subtotal) DESC
        """)

    # Calculer les CA facturés par article
    def calcul_ca_facture_art(self, idclt=False):
        # paramètre du nb de jours glissants pour déterminer la période par défaut
        nb_jr_glissant = self.env['ir.config_parameter'].get_param('nb.jr.glissant.palmares')
        if not nb_jr_glissant:
            nb_jr_glissant = 365
        nb_jr_glissant = int(nb_jr_glissant) - 1  # on enlève un jour car le jour en cours est pris en compte

        # paramètre client
        param_clt1 = ""
        param_clt2 = ""
        if idclt:  # appel depuis bouton recalculer de la fiche client
            param_clt1 = " and fac.partner_id = " + str(idclt)
            param_clt2 = " WHERE s_partner_id = " + str(idclt)
        else:
            # on est sur tous les clients donc en traitement de nuit, donc on remet tous les clients sur une année glissante
            self.env.cr.execute(
                "UPDATE res_partner SET s_period_from = NOW() - INTERVAL '" + str(nb_jr_glissant) + " DAY' ")
            self.env.cr.execute("UPDATE res_partner SET s_period_to = NOW() ")

        # on vide la table des données de tous les clients ou du client passé en paramètre
        self.env.cr.execute("DELETE FROM s_partner_inv_art " + str(param_clt2))

        # on passe une rqte pour calculer le palmarès de tous les clients ou du client passé en paramètre
        self.env.cr.execute("""
            INSERT INTO s_partner_inv_art(s_partner_id,s_product_id,currency_id,s_ca_avt_remise,s_remise_importateur,s_ca_apr_remise)
            SELECT fac.partner_id, fal.product_id, fal.currency_id, 
                sum(fal.quantity*fal.price_unit) AS ca_avt_remise,
                sum(fal.price_subtotal - (fal.quantity*fal.price_unit)) AS remise, 
                sum(fal.price_subtotal) AS ca_apr_remise
            FROM account_move as fac
            INNER JOIN account_move_line AS fal ON fac.id = fal.move_id
            INNER JOIN res_partner AS pa ON fac.partner_id = pa.id
            WHERE fac.state IN ('posted') AND fal.exclude_from_invoice_tab='f'
            AND DATE(fac.invoice_date) >= COALESCE(pa.s_period_from, NOW() - INTERVAL '""" + str(nb_jr_glissant) + """ DAY') AND DATE(fac.invoice_date) <= COALESCE(pa.s_period_to,NOW())
            """ + param_clt1 + """
            GROUP BY fac.partner_id, fal.product_id, fal.currency_id
            ORDER BY sum(fal.price_subtotal) DESC
        """)
