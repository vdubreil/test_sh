from odoo import models, fields, api
import logging
_logger = logging.getLogger("WooCommerce")


class WooCouponDataQueueEpt(models.Model):
    _name = "woo.coupon.data.queue.ept"
    _description = "WooCommerce Coupons Synced Queue Process"

    name = fields.Char(string='Name', copy=False)
    woo_instance_id = fields.Many2one("woo.instance.ept", string="Instances")
    state = fields.Selection([('draft', 'Draft'), ('partial', 'Partially Done'),
                              ("failed", "Failed"), ('done', 'Done')],
                             default='draft', compute="_compute_state", store=True)
    coupon_data_queue_line_ids = fields.One2many('woo.coupon.data.queue.line.ept', 'coupon_data_queue_id', readonly=1)
    common_log_book_id = fields.Many2one("common.log.book.ept",
                                         help="Related Log book which has all logs"
                                              "for current queue.")

    common_log_lines_ids = fields.One2many(related="common_log_book_id.log_lines")
    total_line_count = fields.Integer(compute="_compute_lines", help="Counts total queue lines.")
    draft_line_count = fields.Integer(compute="_compute_lines", help="Counts draft queue lines.")
    failed_line_count = fields.Integer(compute="_compute_lines", help="Counts failed queue lines.")
    done_line_count = fields.Integer(compute="_compute_lines", help="Counts done queue lines.")
    cancelled_line_count = fields.Integer(compute="_compute_lines", help="Counts cancelled queue lines.")
    created_by = fields.Selection([("import", "By Import Process"), ("webhook", "By Webhook")],
                                  help="Identify the process that generated a queue.", default="import")
    is_process_queue = fields.Boolean('Is Processing Queue',default = False)
    running_status = fields.Char(default = "Running...")

    @api.depends("coupon_data_queue_line_ids.state")
    def _compute_lines(self):
        """
        Computes coupon queue lines by different states.
        @author: Nilesh Parmar on Date 28 Dec 2019.
        """
        for record in self:
            queue_lines = record.coupon_data_queue_line_ids
            record.total_line_count = len(queue_lines)
            record.draft_line_count = len(queue_lines.filtered(lambda x: x.state == "draft"))
            record.failed_line_count = len(queue_lines.filtered(lambda x: x.state == "failed"))
            record.done_line_count = len(queue_lines.filtered(lambda x: x.state == "done"))
            record.cancelled_line_count = len(queue_lines.filtered(lambda x: x.state == "cancelled"))

    @api.depends("coupon_data_queue_line_ids.state")
    def _compute_state(self):
        """
        Computes state of coupon queue from queue lines' state.
        @author: Nilesh Parmar on Date 28 Dec 2019.
        """
        for record in self:
            if record.done_line_count == record.total_line_count:
                record.state = "done"
            elif record.draft_line_count == record.total_line_count:
                record.state = "draft"
            elif record.failed_line_count == record.total_line_count:
                record.state = "failed"
            elif record.failed_line_count > 0 or record.draft_line_count > 0:
                record.state = "partial"

    @api.model
    def create(self, vals):
        """
        Inherited Method for giving sequence to ICT.
        @param vals: Dictionary of values.
        @return: New created record.
        @author: Nilesh Parmar on Date 28 Dec 2019.
        """
        record_name = "/"
        sequence_id = self.env.ref("woo_commerce_ept.ir_sequence_coupon_data_queue").id
        if sequence_id:
            record_name = self.env['ir.sequence'].browse(sequence_id).next_by_id()
        vals.update({"name": record_name})
        return super(WooCouponDataQueueEpt, self).create(vals)

    def create_woo_data_queue_lines(self, coupons):
        """
        Creates queue lines from imported JSON data of Coupons.
        @param coupons: coupons in JSON format.
        @author: Nilesh Parmar on Date 28 Dec 2019.
        """
        vals_list = []
        for coupon in coupons:
            vals_list.append({"coupon_data_queue_id":self.id,
                              "woo_coupon":coupon["id"],
                              "coupon_data":coupon,
                              "number": coupon["code"],
                              })
        if vals_list:
            return self.env["woo.coupon.data.queue.line.ept"].create(vals_list)
        return False

    def action_force_done(self):
        """
        Cancels all draft and failed queue lines.
        @author: Nilesh Parmar on Date 28 Dec 2019.
        """
        need_to_cancel_queue_lines = self.coupon_data_queue_line_ids.filtered(lambda x: x.state in ["draft", "failed"])
        need_to_cancel_queue_lines.write({"state":"cancelled"})
        return True

    def open_log_book(self):
        """
        Returns action for opening the related coupon.
        @author: Nilesh Parmar on Date 31 Dec 2019.
        @return: Action to open coupon record.
        """
        return {
            "name":"Logs",
            "type":"ir.actions.act_window",
            "res_model":"common.log.book.ept",
            "res_id":self.common_log_book_id.id,
            "views":[(False, "form")],
            'context': self.env.context
            }

    def create_coupon_queue_from_webhook(self, result, instance):
        """"
        This method used to create a coupon queue from the coupon webhook response and also
        process the queue line.
        @author: Haresh Mori on Date 2-Jan-2020.
        """
        coupon_data_queue = self.env["woo.coupons.ept"].sudo().create_woo_coupon_data_queue(
                instance, [result], created_by="webhook")
        _logger.info(
                "Imported Coupon {0} of {1} via Webhook Successfully.".format(result.get("id"),
                                                                               instance.name))

        coupon_data_queue.coupon_data_queue_line_ids.process_coupon_queue_line()
        _logger.info(
                "Imported Coupon {0} of {1} via Webhook Successfully.".format(result.get("id"),
                                                                                instance.name))

