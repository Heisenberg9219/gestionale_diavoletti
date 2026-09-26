from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import Category, Product, ProductVariant, ProductBarcode, Size, SizeScale
from core.models import Location, TaxRate
from inventory.models import StockBalance, StockMovement
from pricing.models import VariantSalePrice
from purchasing.models import GoodsReceipt
from suppliers.models import Supplier
from documents.models import BusinessDocument, DocumentAttachment, DocumentOcrAnalysis, DocumentType
from documents.services import import_ocr_review_to_inventory, save_ocr_review, validate_ocr_review


class OcrInventoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create(email='ocr-owner@example.test', is_superuser=True)
        cls.supplier = Supplier.objects.create(code='OCR-S', business_name='Fornitore OCR')
        cls.location = Location.objects.create(code='OCR-L', name='Magazzino', type='STOCKROOM')
        cls.category = Category.objects.create(code='OCR-C', name='Abbigliamento')
        cls.tax = TaxRate.objects.create(code='OCR-T', name='IVA', percentage=22)
        scale = SizeScale.objects.create(code='OCR-SC', name='Scala', scale_type='ALPHA')
        cls.size = Size.objects.create(size_scale=scale, code='M', label='M')
        kind = DocumentType.objects.create(code='OCR-INVOICE', name='Fattura acquisto', direction='INCOMING')
        cls.document = BusinessDocument.objects.create(document_type=kind, direction='INCOMING', document_date=date(2026,9,1), title='Fattura', created_by=cls.user)
        cls.attachment = DocumentAttachment.objects.create(document=cls.document, file='documents/original.pdf', original_name='original.pdf', uploaded_by=cls.user)
        cls.analysis = DocumentOcrAnalysis.objects.create(attachment=cls.attachment, provider='AZURE_DOCUMENT_INTELLIGENCE', status='SUCCEEDED', proposed_data={'items': [{'description': 'Originale'}]})

    def setUp(self):
        self.review = {
            'supplier': str(self.supplier.pk), 'location': str(self.location.pk), 'supplier_name': 'Fornitore modificato',
            'invoice_number': 'FA-2026-1', 'invoice_date': '2026-09-01', 'taxable_amount': '20.00', 'tax_rate': '22', 'total_amount': '24.40',
            'items': [{'accepted': True, 'description': 'Descrizione modificata', 'quantity': '2', 'unit_price': '10.00', 'sale_price': '25.00', 'variant_id': '',
                       'new_product': {'name': 'Maglia oceano', 'category': str(self.category.pk), 'tax_rate': str(self.tax.pk), 'size': str(self.size.pk), 'color': '', 'sku': 'OCR-NEW', 'barcode': '123456789'}}]
        }
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = f'/api/v1/documents/attachments/{self.attachment.pk}/'

    def save(self):
        return save_ocr_review(attachment=self.attachment, analysis_id=self.analysis.pk, review=self.review)

    def run_import(self):
        return import_ocr_review_to_inventory(attachment=self.attachment, analysis_id=self.analysis.pk, imported_by=self.user)

    def test_save_api_roundtrip_and_no_inventory_effects(self):
        excluded = deepcopy(self.review['items'][0])
        excluded.update(accepted=False, description='Esclusa', quantity='')
        self.review['items'].append(excluded)
        response = self.client.post(self.url + 'save-review/', {'analysis_id': str(self.analysis.pk), 'review': self.review}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        reopened = self.client.get(f'/api/v1/documents/ocr-analyses/{self.analysis.pk}/').data['proposed_data']
        self.assertEqual(reopened['items'], [{'description': 'Originale'}])
        for key, value in self.review.items():
            self.assertEqual(reopened['review'][key], value)
        self.assertFalse(Product.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.attachment.refresh_from_db()
        self.assertEqual(self.attachment.file.name, 'documents/original.pdf')

    def test_create_product_variant_receipt_stock_cost_and_price(self):
        self.save()
        response = self.client.post(self.url + 'import-to-inventory/', {'analysis_id': str(self.analysis.pk)}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        receipt = GoodsReceipt.objects.get()
        variant = ProductVariant.objects.get(sku='OCR-NEW')
        self.assertEqual(variant.product.name, 'Maglia oceano')
        self.assertEqual(variant.size, self.size)
        self.assertEqual(ProductBarcode.objects.get().variant, variant)
        self.assertEqual(receipt.status, 'CONFIRMED')
        self.assertEqual(receipt.lines.get().unit_cost, Decimal('10'))
        self.assertEqual(StockBalance.objects.get(variant=variant, location=self.location).quantity_on_hand, 2)
        self.assertEqual(StockMovement.objects.get().quantity_delta, 2)
        self.assertEqual(VariantSalePrice.objects.get().amount, Decimal('25'))
        self.document.refresh_from_db()
        self.assertEqual(self.document.source_id, receipt.pk)
        self.assertEqual(self.document.status, 'REGISTERED')
        self.assertEqual(self.document.total_amount, Decimal('24.40'))
        from expenses.models import Expense
        self.assertFalse(Expense.objects.exists())

    def existing_variant(self):
        product = Product.objects.create(code='EXIST', name='Abito primavera', category=self.category, tax_rate=self.tax)
        return ProductVariant.objects.create(product=product, sku='EXIST', size=self.size)

    def test_existing_variant_does_not_create_product(self):
        variant = self.existing_variant()
        self.review['items'][0]['variant_id'] = str(variant.pk)
        self.save()
        self.run_import()
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(ProductVariant.objects.count(), 1)
        self.assertEqual(StockBalance.objects.get().variant, variant)

    def test_duplicates_sku_barcode_similar_name_block_import(self):
        variant = self.existing_variant()
        ProductBarcode.objects.create(variant=variant, code='DUPLICATE', barcode_type='OTHER', source='MANUFACTURER')
        for field, value in [('sku', 'exist'), ('barcode', 'DUPLICATE'), ('name', 'Abito primaverra')]:
            with self.subTest(field=field):
                original = self.review['items'][0]['new_product'][field]
                self.review['items'][0]['new_product'][field] = value
                saved = self.save()
                self.assertTrue(saved.proposed_data['review']['conflicts'])
                with self.assertRaises(ValidationError):
                    self.run_import()
                self.assertFalse(GoodsReceipt.objects.exists())
                self.review['items'][0]['new_product'][field] = original

    def test_internal_duplicates_and_missing_fields(self):
        self.review['items'].append(deepcopy(self.review['items'][0]))
        self.assertTrue(validate_ocr_review(self.review))
        self.review['items'].pop()
        for field, value in [('quantity', '1.5'), ('quantity', 'NaN'), ('sale_price', ''), ('unit_price', 'Infinity')]:
            with self.subTest(field=field, value=value):
                original = self.review['items'][0][field]
                self.review['items'][0][field] = value
                self.assertTrue(validate_ocr_review(self.review))
                self.review['items'][0][field] = original

    def test_failure_after_stock_write_rolls_everything_back(self):
        self.save()
        with patch('purchasing.services._set_variant_sale_price', side_effect=ValidationError('Errore simulato dopo il movimento')):
            with self.assertRaises(ValidationError):
                self.run_import()
        self.assertFalse(Product.objects.exists())
        self.assertFalse(ProductVariant.objects.exists())
        self.assertFalse(GoodsReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.assertFalse(StockBalance.objects.exists())
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.proposed_data['review']['status'], 'SAVED')

    def test_double_import_and_edit_imported_proposal_blocked(self):
        self.save()
        self.run_import()
        with self.assertRaises(ValidationError):
            self.run_import()
        with self.assertRaises(ValidationError):
            self.save()
        another = DocumentOcrAnalysis.objects.create(attachment=self.attachment, provider='AZURE_DOCUMENT_INTELLIGENCE', status='SUCCEEDED', proposed_data={'review': self.review})
        with self.assertRaises(ValidationError):
            import_ocr_review_to_inventory(attachment=self.attachment, analysis_id=another.pk, imported_by=self.user)
        self.assertEqual(GoodsReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_analysis_cannot_be_imported_from_another_attachment(self):
        other = DocumentAttachment.objects.create(document=self.document, file='other.pdf', original_name='other.pdf', uploaded_by=self.user)
        response = self.client.post(f'/api/v1/documents/attachments/{other.pk}/import-to-inventory/', {'analysis_id': str(self.analysis.pk)}, format='json')
        self.assertEqual(response.status_code, 404)
