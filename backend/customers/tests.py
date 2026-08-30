from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from .models import ConsentPurpose, Customer, CustomerConsentEvent
from .services import has_active_consent, record_consent_event


class CustomerConsentServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = Customer.objects.create(
            customer_code="CUSTOMER_TEST_001",
            first_name="Mario",
            last_name="Rossi",
        )
        cls.other_customer = Customer.objects.create(
            customer_code="CUSTOMER_TEST_002",
            first_name="Anna",
            last_name="Verdi",
        )
        cls.standard_purpose = ConsentPurpose.objects.create(
            code="TEST_STANDARD",
            name="Consenso standard test",
            notice_text="Testo informativa versione uno.",
            notice_version="1.0",
            requires_double_opt_in=False,
        )
        cls.double_opt_in_purpose = ConsentPurpose.objects.create(
            code="TEST_DOUBLE_OPT_IN",
            name="Consenso double opt-in test",
            notice_text="Testo double opt-in versione uno.",
            notice_version="1.0",
            requires_double_opt_in=True,
        )

    def test_customer_code_must_be_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Customer.objects.create(
                    customer_code="CUSTOMER_TEST_001",
                    first_name="Cliente",
                    last_name="Duplicato",
                )

    def test_consent_event_keeps_notice_snapshot(self):
        event = record_consent_event(
            customer=self.customer,
            purpose=self.standard_purpose,
            action=CustomerConsentEvent.Action.GRANTED,
            channel=CustomerConsentEvent.Channel.IN_STORE_SMARTPHONE,
        )

        self.standard_purpose.notice_text = "Testo modificato."
        self.standard_purpose.notice_version = "2.0"
        self.standard_purpose.save()

        event.refresh_from_db()
        self.assertEqual(
            event.notice_text,
            "Testo informativa versione uno.",
        )
        self.assertEqual(event.notice_version, "1.0")

    def test_grant_and_withdraw_update_active_status(self):
        record_consent_event(
            customer=self.customer,
            purpose=self.standard_purpose,
            action=CustomerConsentEvent.Action.GRANTED,
            channel=CustomerConsentEvent.Channel.IN_STORE_SMARTPHONE,
        )
        self.assertTrue(
            has_active_consent(
                customer=self.customer,
                purpose=self.standard_purpose,
            )
        )

        record_consent_event(
            customer=self.customer,
            purpose=self.standard_purpose,
            action=CustomerConsentEvent.Action.WITHDRAWN,
            channel=CustomerConsentEvent.Channel.IN_STORE_SMARTPHONE,
        )
        self.assertFalse(
            has_active_consent(
                customer=self.customer,
                purpose=self.standard_purpose,
            )
        )

    def test_double_opt_in_requires_request_and_confirmation(self):
        with self.assertRaises(ValidationError):
            record_consent_event(
                customer=self.customer,
                purpose=self.double_opt_in_purpose,
                action=CustomerConsentEvent.Action.GRANTED,
                channel=CustomerConsentEvent.Channel.WEB,
            )

        request_event = record_consent_event(
            customer=self.customer,
            purpose=self.double_opt_in_purpose,
            action=CustomerConsentEvent.Action.CONFIRMATION_REQUESTED,
            channel=CustomerConsentEvent.Channel.WEB,
        )
        record_consent_event(
            customer=self.customer,
            purpose=self.double_opt_in_purpose,
            action=CustomerConsentEvent.Action.CONFIRMED,
            channel=CustomerConsentEvent.Channel.EMAIL,
            related_event=request_event,
        )

        self.assertTrue(
            has_active_consent(
                customer=self.customer,
                purpose=self.double_opt_in_purpose,
            )
        )

    def test_request_cannot_be_confirmed_twice(self):
        request_event = record_consent_event(
            customer=self.customer,
            purpose=self.double_opt_in_purpose,
            action=CustomerConsentEvent.Action.CONFIRMATION_REQUESTED,
            channel=CustomerConsentEvent.Channel.WEB,
        )
        record_consent_event(
            customer=self.customer,
            purpose=self.double_opt_in_purpose,
            action=CustomerConsentEvent.Action.CONFIRMED,
            channel=CustomerConsentEvent.Channel.EMAIL,
            related_event=request_event,
        )

        with self.assertRaises(ValidationError):
            record_consent_event(
                customer=self.customer,
                purpose=self.double_opt_in_purpose,
                action=CustomerConsentEvent.Action.CONFIRMED,
                channel=CustomerConsentEvent.Channel.EMAIL,
                related_event=request_event,
            )

    def test_confirmation_must_belong_to_same_customer(self):
        request_event = record_consent_event(
            customer=self.customer,
            purpose=self.double_opt_in_purpose,
            action=CustomerConsentEvent.Action.CONFIRMATION_REQUESTED,
            channel=CustomerConsentEvent.Channel.WEB,
        )

        with self.assertRaises(ValidationError):
            record_consent_event(
                customer=self.other_customer,
                purpose=self.double_opt_in_purpose,
                action=CustomerConsentEvent.Action.CONFIRMED,
                channel=CustomerConsentEvent.Channel.EMAIL,
                related_event=request_event,
            )