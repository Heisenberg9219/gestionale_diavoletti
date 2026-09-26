from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework import serializers
from .permissions import IsOwner, IsBusinessOperator


def required(data, name):
    value = data.get(name)
    if value in (None, ""):
        raise ValidationError({name: "Campo obbligatorio."})
    if name in {"quantity", "requested_quantity", "points_delta"}:
        return serializers.IntegerField().run_validation(value)
    if name in {"amount", "initial_amount"}:
        return serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0).run_validation(value)
    if name == "selected_quantities":
        return serializers.DictField(child=serializers.IntegerField(min_value=1), allow_empty=False).run_validation(value)
    return value


def moment(data, name, *, required_value=False):
    value = required(data, name) if required_value else data.get(name)
    if not value:
        return None
    return serializers.DateTimeField().run_validation(value)


def loyalty_activation_viewset(base):
    from loyalty.models import LoyaltyEarningRule
    from loyalty.services import create_earning_activation

    @action(detail=False, methods=("post",))
    def activate(self, request):
        obj = create_earning_activation(
            rule=get_object_or_404(LoyaltyEarningRule, pk=required(request.data, "rule")),
            valid_from=moment(request.data, "valid_from", required_value=True),
            valid_until=moment(request.data, "valid_until"), created_by=request.user,
        )
        return Response(self.get_serializer(obj).data, status=201)

    base.activate = activate
    return base


def loyalty_movement_viewset(base):
    from customers.models import Customer
    from loyalty.models import LoyaltyEarningActivation
    from loyalty.services import get_customer_points_balance, record_point_movement

    @action(detail=False, methods=("get",), url_path="balance")
    def balance(self, request):
        customer = get_object_or_404(Customer, pk=required(request.query_params, "customer"))
        return Response({"customer": str(customer.pk), "points": get_customer_points_balance(customer=customer)})

    @action(detail=False, methods=("post",), url_path="adjust", permission_classes=(IsOwner,))
    def adjust(self, request):
        activation_id = request.data.get("earning_activation")
        obj = record_point_movement(
            customer=get_object_or_404(Customer, pk=required(request.data, "customer")),
            points_delta=serializers.IntegerField().run_validation(required(request.data, "points_delta")),
            movement_type="MANUAL_ADJUSTMENT",
            earning_activation=get_object_or_404(LoyaltyEarningActivation, pk=activation_id) if activation_id else None,
            source_type=request.data.get("source_type", ""), source_id=request.data.get("source_id"),
            occurred_at=moment(request.data, "occurred_at"), notes=request.data.get("notes", ""), created_by=request.user,
        )
        return Response(self.get_serializer(obj).data, status=201)

    base.balance = balance; base.adjust = adjust
    return base


def loyalty_reward_viewset(base):
    from customers.models import Customer
    from loyalty.models import LoyaltyRewardDefinition
    from sales.models import Sale
    from loyalty.services import apply_reward_to_sale, cancel_reward_redemption, issue_loyalty_reward

    @action(detail=False, methods=("post",), url_path="issue")
    def issue(self, request):
        obj = issue_loyalty_reward(
            customer=get_object_or_404(Customer, pk=required(request.data, "customer")),
            definition=get_object_or_404(LoyaltyRewardDefinition, pk=required(request.data, "definition")),
            created_by=request.user, issued_at=moment(request.data, "issued_at"),
        )
        return Response(self.get_serializer(obj).data, status=201)
    @action(detail=True, methods=("post",), url_path="apply-to-sale", permission_classes=(IsBusinessOperator,))
    def apply_to_sale(self, request, pk=None):
        obj = apply_reward_to_sale(reward=self.get_object(), sale=get_object_or_404(Sale, pk=required(request.data, "sale")), applied_by=request.user)
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data, status=201)
    @action(detail=True, methods=("post",), url_path="remove-from-sale", permission_classes=(IsBusinessOperator,))
    def remove_from_sale(self, request, pk=None):
        redemption = self.get_object().redemptions.filter(status="APPLIED").order_by("-created_at").first()
        if redemption is None:
            raise ValidationError("Il premio non e' applicato a una vendita aperta.")
        obj = cancel_reward_redemption(redemption=redemption, cancelled_by=request.user, reason=required(request.data, "reason"))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data)
    base.issue = issue; base.apply_to_sale = apply_to_sale; base.remove_from_sale = remove_from_sale
    return base


def purchasing_order_viewset(base):
    from purchasing.services import send_purchase_order
    @action(detail=True, methods=("post",))
    def send(self, request, pk=None):
        return Response(self.get_serializer(send_purchase_order(order=self.get_object(), sent_by=request.user)).data)
    base.send = send
    return base


def purchasing_receipt_viewset(base):
    from purchasing.services import confirm_goods_receipt
    @action(detail=True, methods=("post",))
    def confirm(self, request, pk=None):
        return Response(self.get_serializer(confirm_goods_receipt(receipt=self.get_object(), confirmed_by=request.user)).data)
    base.confirm = confirm
    return base


def purchasing_invoice_viewset(base):
    from purchasing.services import confirm_supplier_invoice
    from purchasing.api_commands import invoice_receipt_actions
    @action(detail=True, methods=("post",))
    def confirm(self, request, pk=None):
        return Response(self.get_serializer(confirm_supplier_invoice(invoice=self.get_object(), confirmed_by=request.user)).data)
    base.confirm = confirm
    return invoice_receipt_actions(base)


def promotion_campaign_viewset(base):
    from promotions.services import activate_campaign
    @action(detail=True, methods=("post",))
    def activate(self, request, pk=None):
        obj = activate_campaign(campaign=self.get_object(), valid_from=moment(request.data, "valid_from", required_value=True), valid_until=moment(request.data, "valid_until", required_value=True), enabled_by=request.user)
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data, status=201)
    base.activate = activate
    return base


def promotion_activation_viewset(base):
    from promotions.services import cancel_campaign_activation, end_campaign_activation, get_activation_performance
    @action(detail=True, methods=("post",))
    def end(self, request, pk=None): return Response(self.get_serializer(end_campaign_activation(activation=self.get_object(), ended_by=request.user)).data)
    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None): return Response(self.get_serializer(cancel_campaign_activation(activation=self.get_object(), cancelled_by=request.user, cancellation_reason=required(request.data, "reason"))).data)
    @action(detail=True, methods=("get",))
    def performance(self, request, pk=None): return Response(get_activation_performance(activation=self.get_object()))
    base.end=end; base.cancel=cancel; base.performance=performance
    return base


def promotion_offer_viewset(base):
    from catalog.models import ProductVariant
    from promotions.services import apply_offer_to_sale, get_available_offers_for_variant
    from sales.models import Sale
    @action(detail=False, methods=("get",), url_path="available", permission_classes=(IsBusinessOperator,))
    def available(self, request):
        variant=get_object_or_404(ProductVariant, pk=required(request.query_params, "variant"))
        offers=get_available_offers_for_variant(variant=variant, at=moment(request.query_params, "at"))
        return Response(self.get_serializer(offers, many=True).data)
    @action(detail=True, methods=("post",), url_path="apply-to-sale", permission_classes=(IsBusinessOperator,))
    def apply_to_sale(self,request,pk=None):
        obj=apply_offer_to_sale(sale=get_object_or_404(Sale,pk=required(request.data,"sale")),offer=self.get_object(),selected_quantities=required(request.data,"selected_quantities"),operator_selected_quantities=request.data.get("operator_selected_quantities"),applied_by=request.user)
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    base.available=available; base.apply_to_sale=apply_to_sale
    return base


def promotion_application_viewset(base):
    from promotions.services import remove_offer_from_sale
    @action(detail=True,methods=("post",))
    def remove(self,request,pk=None):
        obj=remove_offer_from_sale(application=self.get_object(),removed_by=request.user,removal_reason=required(request.data,"reason"))
        return Response(self.get_serializer(obj).data)
    base.remove=remove
    return base


def voucher_viewset(base):
    from sales.models import Sale
    from vouchers.models import ExpiredVoucherAuthorization, Voucher
    from vouchers.services import authorize_expired_voucher, cancel_voucher, change_voucher_expiry, get_voucher_ledger_balance, issue_voucher, redeem_voucher
    @action(detail=False, methods=("post",), permission_classes=(IsOwner,))
    def issue(self, request):
        obj=issue_voucher(voucher_type=required(request.data,"voucher_type"), initial_amount=required(request.data,"initial_amount"), issued_by=request.user, code=request.data.get("code"), expires_at=moment(request.data,"expires_at"), holder_first_name=request.data.get("holder_first_name",""), holder_last_name=request.data.get("holder_last_name",""), source_type=request.data.get("source_type",""), source_id=request.data.get("source_id"), notifications_enabled=request.data.get("notifications_enabled",False), notes=request.data.get("notes",""))
        return Response(self.get_serializer(obj).data,status=201)
    @action(detail=True, methods=("get",))
    def balance(self,request,pk=None): return Response({"balance":get_voucher_ledger_balance(voucher=self.get_object())})
    @action(detail=True, methods=("post",),url_path="change-expiry", permission_classes=(IsOwner,))
    def change_expiry(self,request,pk=None):
        obj = change_voucher_expiry(voucher=self.get_object(),new_expires_at=moment(request.data,"expires_at",required_value=True),reason=required(request.data,"reason"),changed_by=request.user)
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data)
    @action(detail=True, methods=("post",),url_path="authorize-expired", permission_classes=(IsOwner,))
    def authorize_expired(self,request,pk=None):
        obj=authorize_expired_voucher(voucher=self.get_object(),sale=get_object_or_404(Sale,pk=required(request.data,"sale")),authorized_by=request.user,reason=required(request.data,"reason"))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    @action(detail=True, methods=("post",))
    def redeem(self,request,pk=None):
        auth=request.data.get("expired_authorization")
        obj=redeem_voucher(voucher=self.get_object(),sale=get_object_or_404(Sale,pk=required(request.data,"sale")),requested_amount=required(request.data,"amount"),created_by=request.user,expired_authorization=get_object_or_404(ExpiredVoucherAuthorization,pk=auth) if auth else None)
        from .factories import serializer_for
        movement, payment = obj
        return Response({"movement": serializer_for(type(movement))(movement).data, "payment": serializer_for(type(payment))(payment).data},status=201)
    @action(detail=True, methods=("post",), permission_classes=(IsOwner,))
    def cancel(self,request,pk=None): return Response(self.get_serializer(cancel_voucher(voucher=self.get_object(),cancelled_by=request.user,reason=required(request.data,"reason"))).data)
    base.issue=issue; base.balance=balance; base.change_expiry=change_expiry; base.authorize_expired=authorize_expired; base.redeem=redeem; base.cancel=cancel
    return base


def gift_list_viewset(base):
    from notifications.services import generate_gift_list_notifications
    from catalog.models import ProductVariant
    from giftlists.services import add_contribution, authorize_reserved_stock_sale, close_gift_list, set_gift_list_item
    from sales.models import Sale
    @action(detail=True, methods=("post",), url_path="set-item")
    def set_item(self,request,pk=None):
        obj=set_gift_list_item(gift_list=self.get_object(),variant=get_object_or_404(ProductVariant,pk=required(request.data,"variant")),requested_quantity=required(request.data,"requested_quantity"),reserved_quantity=request.data.get("reserved_quantity",0),added_by=request.user,notes=request.data.get("notes",""))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    @action(detail=True, methods=("post",), url_path="add-contribution")
    def contribution(self,request,pk=None):
        obj=add_contribution(gift_list=self.get_object(),first_name=required(request.data,"first_name"),last_name=required(request.data,"last_name"),amount=required(request.data,"amount"),payment_method=required(request.data,"payment_method"),recorded_by=request.user,occurred_at=moment(request.data,"occurred_at"),notes=request.data.get("notes",""))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    @action(detail=True, methods=("post",), url_path="authorize-stock")
    def authorize_stock(self,request,pk=None):
        obj=authorize_reserved_stock_sale(sale=get_object_or_404(Sale,pk=required(request.data,"sale")),variant=get_object_or_404(ProductVariant,pk=required(request.data,"variant")),quantity=required(request.data,"quantity"),authorized_by=request.user,reason=required(request.data,"reason"))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    @action(detail=True, methods=("post",))
    def close(self,request,pk=None):
        gift_list, voucher = close_gift_list(gift_list=self.get_object(),closed_by=request.user)
        from .factories import serializer_for
        return Response({"gift_list": self.get_serializer(gift_list).data, "voucher": serializer_for(type(voucher))(voucher).data if voucher else None})
    @action(detail=False, methods=("post",), url_path="refresh-notifications")
    def refresh_notifications(self, request): return Response({"count": len(generate_gift_list_notifications(users=(request.user,)))})
    base.set_item=set_item; base.contribution=contribution; base.authorize_stock=authorize_stock; base.close=close; base.refresh_notifications=refresh_notifications
    return base


def expense_viewset(base):
    from expenses.services import add_expense_payment, cancel_expense, open_expense
    from notifications.services import generate_expense_due_notifications
    @action(detail=True,methods=("post",))
    def open(self,request,pk=None): return Response(self.get_serializer(open_expense(expense=self.get_object(),opened_by=request.user)).data)
    @action(detail=True,methods=("post",),url_path="add-payment")
    def add_payment(self,request,pk=None):
        obj=add_expense_payment(expense=self.get_object(),amount=required(request.data,"amount"),payment_method=required(request.data,"payment_method"),recorded_by=request.user,paid_at=moment(request.data,"paid_at"),reference=request.data.get("reference",""),notes=request.data.get("notes",""))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    @action(detail=True,methods=("post",))
    def cancel(self,request,pk=None): return Response(self.get_serializer(cancel_expense(expense=self.get_object(),cancelled_by=request.user,reason=required(request.data,"reason"))).data)
    @action(detail=False, methods=("post",), url_path="refresh-due-notifications")
    def refresh_due_notifications(self, request):
        notifications = generate_expense_due_notifications(users=(request.user,))
        return Response({"count": len(notifications)})
    base.open=open; base.add_payment=add_payment; base.cancel=cancel; base.refresh_due_notifications=refresh_due_notifications
    return base


def document_viewset(base):
    from documents.models import DocumentAttachment
    from documents.services import cancel_document, finalize_document
    @action(detail=True,methods=("post",))
    def finalize(self,request,pk=None): return Response(self.get_serializer(finalize_document(document=self.get_object(),finalized_by=request.user,number=request.data.get("number"))).data)
    @action(detail=True,methods=("post",))
    def cancel(self,request,pk=None): return Response(self.get_serializer(cancel_document(document=self.get_object(),cancelled_by=request.user,reason=required(request.data,"reason"))).data)
    @action(detail=True, methods=("post",), url_path="upload-attachment", parser_classes=(MultiPartParser, FormParser))
    def upload_attachment(self, request, pk=None):
        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            raise ValidationError({"file": "Allega un file PDF."})
        attachment = DocumentAttachment.objects.create(
            document=self.get_object(),
            file=uploaded_file,
            original_name=uploaded_file.name,
            description=request.data.get("description", ""),
            uploaded_by=request.user,
        )
        from .factories import serializer_for
        return Response(serializer_for(DocumentAttachment)(attachment).data, status=201)
    base.finalize=finalize; base.cancel=cancel; base.upload_attachment=upload_attachment
    return base


def document_attachment_viewset(base):
    from core.models import Location
    from documents.services import analyze_invoice_attachment_with_azure, import_ocr_review_to_inventory, save_ocr_review, validate_ocr_review
    from documents.models import DocumentOcrAnalysis
    from suppliers.models import Supplier

    @action(detail=True, methods=("post",), url_path="analyze-invoice")
    def analyze_invoice(self, request, pk=None):
        analysis = analyze_invoice_attachment_with_azure(
            attachment=self.get_object(),
            requested_by=request.user,
        )
        from .factories import serializer_for
        if analysis.status != "SUCCEEDED":
            return Response(
                {"detail": analysis.error_message or "L'analisi OCR non è stata completata."},
                status=422,
            )
        return Response(serializer_for(type(analysis))(analysis).data, status=201)

    @action(detail=True, methods=("post",), url_path="import-to-inventory")
    def import_to_inventory(self, request, pk=None):
        analysis = get_object_or_404(DocumentOcrAnalysis, pk=required(request.data, "analysis_id"), attachment=self.get_object(), status="SUCCEEDED")
        receipt = import_ocr_review_to_inventory(
            attachment=self.get_object(),
            imported_by=request.user,
            analysis_id=analysis.pk,
        )
        from .factories import serializer_for
        return Response(serializer_for(type(receipt))(receipt).data, status=201)

    @action(detail=True, methods=("post",), url_path="save-review")
    def save_review(self, request, pk=None):
        attachment = self.get_object()
        analysis = get_object_or_404(DocumentOcrAnalysis, pk=required(request.data, "analysis_id"), attachment=attachment, status="SUCCEEDED")
        analysis = save_ocr_review(attachment=attachment, analysis_id=analysis.pk, review=required(request.data, "review"))
        from .factories import serializer_for
        return Response(serializer_for(DocumentOcrAnalysis)(analysis).data)

    @action(detail=True, methods=("post",), url_path="validate-review")
    def validate_review(self, request, pk=None):
        self.get_object()
        review = request.data.get("review")
        if not isinstance(review, dict):
            return Response({"detail": "Proposta non valida."}, status=400)
        return Response({"conflicts": validate_ocr_review(review)})

    base.save_review = save_review; base.validate_review = validate_review
    base.analyze_invoice = analyze_invoice; base.import_to_inventory = import_to_inventory
    return base


def return_viewset(base):
    from returns.services import cancel_draft_return, confirm_customer_return, create_customer_return, set_return_line
    from sales.models import Sale, SaleLine
    @action(detail=False,methods=("post",),url_path="create-draft")
    def create_draft(self,request):
        obj=create_customer_return(original_sale=get_object_or_404(Sale,pk=required(request.data,"original_sale")),reason=required(request.data,"reason"),created_by=request.user,notes=request.data.get("notes",""))
        return Response(self.get_serializer(obj).data,status=201)
    @action(detail=True,methods=("post",),url_path="set-line")
    def set_line(self,request,pk=None):
        obj=set_return_line(customer_return=self.get_object(),original_sale_line=get_object_or_404(SaleLine,pk=required(request.data,"original_sale_line")),quantity=required(request.data,"quantity"),restock=request.data.get("restock",True))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data)
    @action(detail=True,methods=("post",))
    def confirm(self,request,pk=None): return Response(self.get_serializer(confirm_customer_return(customer_return=self.get_object(),confirmed_by=request.user)).data)
    @action(detail=True,methods=("post",))
    def cancel(self,request,pk=None): return Response(self.get_serializer(cancel_draft_return(customer_return=self.get_object(),cancelled_by=request.user,reason=required(request.data,"reason"))).data)
    base.create_draft=create_draft; base.set_line=set_line; base.confirm=confirm; base.cancel=cancel
    return base


def reorder_viewset(base):
    from notifications.services import generate_reorder_notifications
    from catalog.models import ProductVariant
    from core.models import Location
    from purchasing.models import PurchaseOrderLine
    from reorders.services import add_to_reorder_list, complete_reorder, get_pending_reorders_by_supplier, link_reorder_to_purchase_order, remove_from_reorder_list, update_pending_reorder
    from suppliers.models import Supplier
    @action(detail=False,methods=("post",))
    def add(self,request):
        supplier=request.data.get("supplier")
        obj=add_to_reorder_list(variant=get_object_or_404(ProductVariant,pk=required(request.data,"variant")),location=get_object_or_404(Location,pk=required(request.data,"location")),added_by=request.user,requested_quantity=request.data.get("requested_quantity"),supplier=get_object_or_404(Supplier,pk=supplier) if supplier else None,reason=request.data.get("reason",""),notes=request.data.get("notes",""))
        return Response(self.get_serializer(obj).data,status=201)
    @action(detail=True,methods=("post",))
    def update_pending(self,request,pk=None):
        supplier=request.data.get("supplier")
        return Response(self.get_serializer(update_pending_reorder(reorder_item=self.get_object(),requested_quantity=required(request.data,"requested_quantity"),updated_by=request.user,supplier=get_object_or_404(Supplier,pk=supplier) if supplier else None,notes=request.data.get("notes"))).data)
    @action(detail=True,methods=("post",))
    def remove(self,request,pk=None): return Response(self.get_serializer(remove_from_reorder_list(reorder_item=self.get_object(),removed_by=request.user,reason=request.data.get("reason",""))).data)
    @action(detail=True,methods=("post",),url_path="link-order-line")
    def link(self,request,pk=None): return Response(self.get_serializer(link_reorder_to_purchase_order(reorder_item=self.get_object(),purchase_order_line=get_object_or_404(PurchaseOrderLine,pk=required(request.data,"purchase_order_line")),ordered_by=request.user)).data)
    @action(detail=True,methods=("post",))
    def complete(self,request,pk=None): return Response(self.get_serializer(complete_reorder(reorder_item=self.get_object(),completed_by=request.user)).data)
    @action(detail=False,methods=("get",),url_path="grouped-by-supplier")
    def grouped(self,request):
        return Response([{"supplier": str(group["supplier"].pk) if group["supplier"] else None, "items": self.get_serializer(group["items"], many=True).data} for group in get_pending_reorders_by_supplier()])
    @action(detail=False, methods=("post",), url_path="refresh-notifications")
    def refresh_notifications(self, request): return Response({"count": len(generate_reorder_notifications(users=(request.user,)))})
    base.add=add; base.update_pending=update_pending; base.remove=remove; base.link=link; base.complete=complete; base.grouped=grouped; base.refresh_notifications=refresh_notifications
    return base


def reporting_widget_viewset(base):
    from reporting.services import calculate_widget, refresh_widget
    @action(detail=True,methods=("get",))
    def calculate(self,request,pk=None): return Response(calculate_widget(self.get_object()))
    @action(detail=True,methods=("post",))
    def refresh(self,request,pk=None):
        obj=refresh_widget(self.get_object(),user=request.user)
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data,status=201)
    @action(detail=True, methods=("post",), url_path="export-csv")
    def export_csv(self, request, pk=None):
        import csv
        import io
        from django.http import HttpResponse
        from django.utils import timezone
        from reporting.models import ReportExport
        widget = self.get_object()
        result = calculate_widget(widget)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["label", "value", "date_from", "date_to"])
        for row in result["series"] or [{"label": widget.title, "value": result["value"]}]:
            label = str(row["label"])
            if label.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
                label = "'" + label
            writer.writerow([label, row["value"], result["date_from"], result["date_to"]])
        filename = f"report-{widget.pk}.csv"
        ReportExport.objects.create(widget=widget, export_format="CSV", status="COMPLETED", requested_by=request.user, completed_at=timezone.now(), file_name=filename)
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    @action(detail=True, methods=("post",), url_path="export-xlsx")
    def export_xlsx(self, request, pk=None):
        from io import BytesIO
        from django.http import HttpResponse
        from django.utils import timezone
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from reporting.models import ReportExport
        widget = self.get_object()
        result = calculate_widget(widget)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Report"
        sheet.append(["Etichetta", "Valore", "Dal", "Al"])
        for row in result["series"] or [{"label": widget.title, "value": result["value"]}]:
            sheet.append([str(row["label"]), str(row["value"]), result["date_from"], result["date_to"]])
        for cell in sheet[1]: cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(max(len(str(cell.value or "")) for cell in column) + 2, 50)
        content = BytesIO(); workbook.save(content)
        filename = f"report-{widget.pk}.xlsx"
        ReportExport.objects.create(widget=widget, export_format="XLSX", status="COMPLETED", requested_by=request.user, completed_at=timezone.now(), file_name=filename)
        response = HttpResponse(content.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    base.calculate=calculate; base.refresh=refresh; base.export_csv=export_csv; base.export_xlsx=export_xlsx
    return base


def gift_item_viewset(base):
    from giftlists.services import record_item_purchase
    from sales.models import SaleLine
    @action(detail=True, methods=("post",), url_path="record-purchase")
    def record_purchase(self, request, pk=None):
        line = get_object_or_404(SaleLine, pk=required(request.data, "sale_line"))
        if line.sale.status != "CONFIRMED":
            raise ValidationError("Confermare prima la vendita.")
        obj = record_item_purchase(item=self.get_object(), sale_line=line, quantity=required(request.data, "quantity"), recorded_by=request.user)
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data, status=201)
    base.record_purchase = record_purchase
    return base


def notification_delivery_viewset(base):
    from notifications.services import archive_notification, mark_notification_read
    original=base.get_queryset
    def get_queryset(self): return original(self).filter(user=self.request.user)
    @action(detail=True,methods=("post",),url_path="mark-read")
    def mark_read(self,request,pk=None): return Response(self.get_serializer(mark_notification_read(delivery=self.get_object())).data)
    @action(detail=True,methods=("post",))
    def archive(self,request,pk=None): return Response(self.get_serializer(archive_notification(delivery=self.get_object())).data)
    base.get_queryset=get_queryset; base.mark_read=mark_read; base.archive=archive
    return base


def notification_viewset(base):
    from notifications.services import resolve_notification
    original=base.get_queryset
    def get_queryset(self):
        return original(self).filter(deliveries__user=self.request.user).distinct()
    @action(detail=True, methods=("post",), permission_classes=(IsOwner,))
    def resolve(self, request, pk=None):
        obj = resolve_notification(notification=self.get_object(), resolved_by=request.user, notes=required(request.data, "notes"))
        from .factories import serializer_for
        return Response(serializer_for(type(obj))(obj).data)
    base.get_queryset=get_queryset; base.resolve=resolve
    return base


def notification_resolution_viewset(base):
    original=base.get_queryset
    def get_queryset(self):
        return original(self).filter(notification__deliveries__user=self.request.user).distinct()
    base.get_queryset=get_queryset
    return base


def integration_sync_viewset(base):
    from integrations.services import enqueue_inventory_sync, process_sync_event
    from catalog.models import ProductVariant
    from core.models import Location
    @action(detail=False,methods=("post",),url_path="enqueue-inventory")
    def enqueue(self,request):
        location=request.data.get("location")
        objects=enqueue_inventory_sync(variant=get_object_or_404(ProductVariant,pk=required(request.data,"variant")),location=get_object_or_404(Location,pk=location) if location else None)
        return Response(self.get_serializer(objects,many=True).data,status=201)
    @action(detail=True, methods=("post",), url_path="process")
    def process(self, request, pk=None):
        return Response(self.get_serializer(process_sync_event(event=self.get_object())).data)
    base.enqueue=enqueue; base.process=process
    return base
