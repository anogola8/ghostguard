from django.test import TestCase
from django.urls import reverse
from apps.beneficiaries.models import Beneficiary, normalize_phone, hash_id_reference
from apps.audit.models import AuditEntry, EventType
from apps.programs.models import Program

class BeneficiaryTests(TestCase):
    def test_phone_normalization(self):
        self.assertEqual(normalize_phone("0712345678"), "+254712345678")
        self.assertEqual(normalize_phone("254712345678"), "+254712345678")
        self.assertEqual(normalize_phone("+254712345678"), "+254712345678")

    def test_id_hashing(self):
        hashed, salt = hash_id_reference("12345678")
        self.assertNotEqual(hashed, "12345678")
        self.assertEqual(len(hashed), 64)
        self.assertTrue(len(salt) > 0)

    def test_registration_view_and_audit_hook(self):
        from apps.accounts.models import User
        user = User.objects.create_user(username="field", password="pw", role="FIELD_OFFICER")
        self.client.force_login(user)
        
        program = Program.objects.create(name="Relief A", start_date="2026-01-01", end_date="2026-12-31")
        
        response = self.client.post(reverse("beneficiaries:register"), {
            "program": program.id,
            "full_name": "John Doe",
            "phone": "0712345678",
            "village": "Nairobi",
            "raw_id_reference": "12345678",
            "device_id": "test-agent"
        })
        
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Beneficiary.objects.count(), 1)
        
        b = Beneficiary.objects.first()
        self.assertEqual(b.phone, "+254712345678")
        self.assertNotEqual(b.id_reference_hash, "12345678")
        
        # Check audit log
        self.assertEqual(AuditEntry.objects.count(), 1)
        entry = AuditEntry.objects.first()
        self.assertEqual(entry.event_type, EventType.BENEFICIARY_REGISTERED)
        self.assertEqual(entry.payload["name"], "John Doe")
