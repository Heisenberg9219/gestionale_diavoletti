from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from core.models import UUIDTimeStampedModel


class GiftList(UUIDTimeStampedModel):
    class Type(models.TextChoices):
        BIRTH = "BIRTH", "Lista nascita"
        BIRTHDAY = "BIRTHDAY", "Lista compleanno"

    class Mode(models.TextChoices):
        PRODUCTS = "PRODUCTS", "Articoli"
        CONTRIBUTIONS = "CONTRIBUTIONS", "Contributi"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Aperta"
        CLOSED = "CLOSED", "Chiusa"
        CANCELLED = "CANCELLED", "Annullata"

    code = models.CharField(max_length=48, unique=True)
    list_type = models.CharField(max_length=16, choices=Type.choices)
    mode = models.CharField(max_length=16, choices=Mode.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    title = models.CharField(max_length=160)
    beneficiary_first_name = models.CharField(max_length=120)
    beneficiary_last_name = models.CharField(max_length=120)
    event_date = models.DateField(null=True, blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    contact_email = models.EmailField(blank=True)
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gift_lists",
    )
    location = models.ForeignKey(
        "core.Location",
        on_delete=models.PROTECT,
        related_name="gift_lists",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_gift_lists",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="closed_gift_lists",
    )
    generated_voucher = models.OneToOneField(
        "vouchers.Voucher",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_gift_list",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_gift_lists",
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    notifications_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("status", "list_type"),
                name="giftlist_status_type_idx",
            ),
            models.Index(
                fields=("beneficiary_last_name", "beneficiary_first_name"),
                name="giftlist_benef_name_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(~Q(list_type="BIRTH") | Q(mode="PRODUCTS")),
                name="giftlist_birth_products_only",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="CLOSED")
                    | Q(closed_at__isnull=False, closed_by__isnull=False)
                ),
                name="giftlist_closed_audit",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.title}"


class GiftListItem(UUIDTimeStampedModel):
    gift_list = models.ForeignKey(
        GiftList,
        on_delete=models.PROTECT,
        related_name="items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="gift_list_items",
    )
    requested_quantity = models.PositiveIntegerField(default=1)
    reserved_quantity = models.PositiveIntegerField(default=1)
    purchased_quantity = models.PositiveIntegerField(default=0)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_gift_list_items",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("gift_list", "variant"),
                name="giftlist_item_variant_unique",
            ),
            models.CheckConstraint(
                condition=Q(requested_quantity__gt=0),
                name="giftlist_item_requested_pos",
            ),
            models.CheckConstraint(
                condition=(
                    Q(reserved_quantity__lte=F("requested_quantity"))
                    & Q(purchased_quantity__lte=F("requested_quantity"))
                ),
                name="giftlist_item_quantities_ok",
            ),
        ]

    @property
    def remaining_reserved_quantity(self):
        return max(self.reserved_quantity - self.purchased_quantity, 0)

    def __str__(self):
        return f"{self.gift_list.code} - {self.variant.sku}"


class GiftListContribution(UUIDTimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Contanti"
        CARD = "CARD", "Carta"
        OTHER = "OTHER", "Altro"

    gift_list = models.ForeignKey(
        GiftList,
        on_delete=models.PROTECT,
        related_name="contributions",
    )
    contributor_first_name = models.CharField(max_length=120)
    contributor_last_name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=16,
        choices=PaymentMethod.choices,
    )
    occurred_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_gift_list_contributions",
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("occurred_at", "created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="giftlist_contribution_positive",
            ),
        ]

    def __str__(self):
        return f"{self.gift_list.code}: {self.amount}"


class GiftListItemPurchase(UUIDTimeStampedModel):
    item = models.ForeignKey(
        GiftListItem,
        on_delete=models.PROTECT,
        related_name="purchases",
    )
    sale_line = models.ForeignKey(
        "sales.SaleLine",
        on_delete=models.PROTECT,
        related_name="gift_list_purchases",
    )
    quantity = models.PositiveIntegerField()
    sold_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_gift_list_purchases",
    )

    class Meta:
        ordering = ("sold_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("item", "sale_line"),
                name="giftlist_item_sale_unique",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="giftlist_purchase_qty_pos",
            ),
        ]


class ReservedStockSaleAuthorization(UUIDTimeStampedModel):
    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="reserved_stock_authorizations",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="reserved_stock_sale_authorizations",
    )
    requested_sale_quantity = models.PositiveIntegerField()
    stock_quantity_snapshot = models.PositiveIntegerField()
    reserved_quantity_snapshot = models.PositiveIntegerField()
    affected_list_codes = models.JSONField(default=list)
    reason = models.CharField(max_length=255)
    authorized_at = models.DateTimeField(default=timezone.now)
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authorized_reserved_stock_sales",
    )

    class Meta:
        ordering = ("-authorized_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_sale_quantity__gt=0),
                name="giftlist_auth_sale_qty_pos",
            ),
            models.CheckConstraint(
                condition=Q(reserved_quantity_snapshot__gt=0),
                name="giftlist_auth_reserved_pos",
            ),
        ]

    def __str__(self):
        return f"{self.sale} - {self.variant.sku}"
