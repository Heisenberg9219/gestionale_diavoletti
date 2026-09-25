from django.urls import include, path
from rest_framework.routers import DefaultRouter

from documents.models import BusinessDocument, DocumentAttachment, DocumentOcrAnalysis, DocumentStatusChange, DocumentType
from expenses.models import Expense, ExpenseAttachment, ExpenseCategory, ExpensePayment, ExpenseStatusChange
from giftlists.models import GiftList, GiftListContribution, GiftListItem, GiftListItemPurchase, ReservedStockSaleAuthorization
from integrations.models import ExternalObjectMapping, ImportedOrder, IntegrationConnection, SyncEvent, WebhookEvent
from loyalty.models import IssuedLoyaltyReward, LoyaltyEarningActivation, LoyaltyEarningRule, LoyaltyPointMovement, LoyaltyRewardDefinition
from notifications.models import Notification, NotificationDelivery, NotificationResolution
from promotions.models import CampaignOffer, OfferBrandScope, OfferCategoryScope, OfferProductScope, OfferSeasonScope, OfferSupplierScope, OfferVariantScope, PromotionCampaign, PromotionCampaignActivation, PromotionRule, SalePromotionAllocation, SalePromotionApplication
from purchasing.models import GoodsReceipt, GoodsReceiptLine, PurchaseCostAdjustment, PurchaseOrder, PurchaseOrderLine, SupplierInvoice, SupplierInvoiceLine, SupplierInvoiceReceipt
from reorders.models import ReorderItem, ReorderItemChange, ReorderNotificationLink
from reporting.models import ReportDashboard, ReportExport, ReportSnapshot, ReportWidget
from returns.models import CustomerReturn, CustomerReturnLine
from vouchers.models import ExpiredVoucherAuthorization, Voucher, VoucherExpiryChange, VoucherMovement

from .factories import viewset_for
from .workflows import (
    document_viewset, document_attachment_viewset, expense_viewset, gift_list_viewset, gift_item_viewset,
    document_ocr_analysis_viewset,
    integration_sync_viewset, loyalty_activation_viewset,
    loyalty_movement_viewset, loyalty_reward_viewset,
    notification_delivery_viewset, notification_resolution_viewset,
    notification_viewset, promotion_activation_viewset,
    promotion_application_viewset, promotion_campaign_viewset,
    promotion_offer_viewset, purchasing_invoice_viewset,
    purchasing_order_viewset, purchasing_receipt_viewset,
    reorder_viewset, reporting_widget_viewset, return_viewset,
    voucher_viewset,
)


WORKFLOWS = {
    LoyaltyEarningActivation: loyalty_activation_viewset,
    LoyaltyPointMovement: loyalty_movement_viewset,
    IssuedLoyaltyReward: loyalty_reward_viewset,
    PurchaseOrder: purchasing_order_viewset,
    GoodsReceipt: purchasing_receipt_viewset,
    SupplierInvoice: purchasing_invoice_viewset,
    PromotionCampaign: promotion_campaign_viewset,
    PromotionCampaignActivation: promotion_activation_viewset,
    CampaignOffer: promotion_offer_viewset,
    SalePromotionApplication: promotion_application_viewset,
    Voucher: voucher_viewset,
    GiftList: gift_list_viewset,
    GiftListItem: gift_item_viewset,
    Expense: expense_viewset,
    BusinessDocument: document_viewset,
    DocumentAttachment: document_attachment_viewset,
    DocumentOcrAnalysis: document_ocr_analysis_viewset,
    Notification: notification_viewset,
    NotificationDelivery: notification_delivery_viewset,
    NotificationResolution: notification_resolution_viewset,
    CustomerReturn: return_viewset,
    ReorderItem: reorder_viewset,
    SyncEvent: integration_sync_viewset,
    ReportWidget: reporting_widget_viewset,
}


def router_for(entries):
    router = DefaultRouter()
    for prefix, model, mode, read_only in entries:
        viewset = viewset_for(model, mode=mode, read_only=read_only)
        if model in WORKFLOWS:
            viewset = WORKFLOWS[model](viewset)
        router.register(prefix, viewset, basename=prefix)
    return router


routers = {
    "loyalty": router_for([
        ("earning-rules", LoyaltyEarningRule, "owner", False), ("earning-activations", LoyaltyEarningActivation, "owner", True),
        ("point-movements", LoyaltyPointMovement, "read", True), ("reward-definitions", LoyaltyRewardDefinition, "owner", False),
        ("issued-rewards", IssuedLoyaltyReward, "read", True),
    ]),
    "purchasing": router_for([
        ("orders", PurchaseOrder, "owner", False), ("order-lines", PurchaseOrderLine, "owner", False),
        ("receipts", GoodsReceipt, "owner", False), ("receipt-lines", GoodsReceiptLine, "owner", False),
        ("invoices", SupplierInvoice, "owner", False), ("invoice-lines", SupplierInvoiceLine, "owner", False),
        ("invoice-receipts", SupplierInvoiceReceipt, "owner", True), ("cost-adjustments", PurchaseCostAdjustment, "owner", True),
    ]),
    "promotions": router_for([
        ("campaigns", PromotionCampaign, "owner", False), ("activations", PromotionCampaignActivation, "owner", True),
        ("rules", PromotionRule, "owner", False), ("offers", CampaignOffer, "owner", False),
        ("offer-categories", OfferCategoryScope, "owner", False), ("offer-brands", OfferBrandScope, "owner", False),
        ("offer-seasons", OfferSeasonScope, "owner", False), ("offer-suppliers", OfferSupplierScope, "owner", False),
        ("offer-products", OfferProductScope, "owner", False), ("offer-variants", OfferVariantScope, "owner", False),
        ("applications", SalePromotionApplication, "read", True), ("allocations", SalePromotionAllocation, "read", True),
    ]),
    "vouchers": router_for([
        ("vouchers", Voucher, "operator", True), ("movements", VoucherMovement, "read", True),
        ("expiry-changes", VoucherExpiryChange, "read", True), ("expired-authorizations", ExpiredVoucherAuthorization, "read", True),
    ]),
    "gift-lists": router_for([
        ("lists", GiftList, "operator", False), ("items", GiftListItem, "operator", True),
        ("contributions", GiftListContribution, "operator", True), ("purchases", GiftListItemPurchase, "operator", True),
        ("stock-authorizations", ReservedStockSaleAuthorization, "operator", True),
    ]),
    "expenses": router_for([
        ("categories", ExpenseCategory, "owner", False), ("expenses", Expense, "owner", False),
        ("payments", ExpensePayment, "owner", True), ("attachments", ExpenseAttachment, "owner", False),
        ("status-changes", ExpenseStatusChange, "owner", True),
    ]),
    "documents": router_for([
        ("types", DocumentType, "owner", False), ("documents", BusinessDocument, "owner", False),
        ("attachments", DocumentAttachment, "owner", True), ("ocr-analyses", DocumentOcrAnalysis, "owner", True), ("status-changes", DocumentStatusChange, "owner", True),
    ]),
    "notifications": router_for([
        ("notifications", Notification, "read", True), ("deliveries", NotificationDelivery, "read", True),
        ("resolutions", NotificationResolution, "read", True),
    ]),
    "returns": router_for([
        ("returns", CustomerReturn, "operator", True), ("lines", CustomerReturnLine, "operator", True),
    ]),
    "reorders": router_for([
        ("items", ReorderItem, "owner", True), ("changes", ReorderItemChange, "owner", True),
        ("notification-links", ReorderNotificationLink, "owner", True),
    ]),
    "integrations": router_for([
        ("connections", IntegrationConnection, "owner", False), ("mappings", ExternalObjectMapping, "owner", False),
        ("sync-events", SyncEvent, "owner", True), ("webhooks", WebhookEvent, "owner", True), ("orders", ImportedOrder, "owner", True),
    ]),
    "reporting": router_for([
        ("dashboards", ReportDashboard, "owner", False), ("widgets", ReportWidget, "owner", False),
        ("snapshots", ReportSnapshot, "owner", True), ("exports", ReportExport, "owner", True),
    ]),
}

urlpatterns = [path(f"{name}/", include(router.urls)) for name, router in routers.items()]
