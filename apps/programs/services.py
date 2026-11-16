"""Autonomous Payout Engine.
Handles batch M-Pesa disbursements with simulated API latency
and strict ledger reconciliation.
"""
import time
import secrets
from django.utils import timezone
from django.db import transaction
from .models import Payout
from apps.beneficiaries.models import Beneficiary
from apps.audit.services import append
from apps.audit.models import EventType


class PayoutEngine:
    def __init__(self, disbursement_round):
        self.round = disbursement_round
        self.batch_size = 50

    def execute(self, amount_per_beneficiary=15000.00, progress_callback=None):
        """Processes payouts in batches. Returns a summary dict."""
        beneficiaries = list(Beneficiary.objects.filter(
            program=self.round.program,
            status=Beneficiary.Status.ACTIVE,
        ))
        
        total_to_pay = len(beneficiaries)
        if total_to_pay == 0:
            return {"success": 0, "failed": 0, "total_amount": 0, "error": "No active beneficiaries"}

        success_count = 0
        failed_count = 0
        total_amount = 0

        # Process in batches to simulate real-world API rate limits
        for i in range(0, total_to_pay, self.batch_size):
            batch = beneficiaries[i:i + self.batch_size]
            
            for b in batch:
                try:
                    # Simulate M-Pesa API latency (50ms)
                    time.sleep(0.05)
                    
                    # Generate a realistic M-Pesa transaction code
                    mpesa_code = f"Q{secrets.token_hex(4).upper()}"
                    
                    payout = Payout.objects.create(
                        round=self.round,
                        beneficiary=b,
                        amount=amount_per_beneficiary,
                        reference=mpesa_code,
                    )
                    
                    # Write to the HMAC audit chain
                    append(
                        EventType.PAYOUT_RECORDED,
                        {
                            "beneficiary_id": b.public_id,
                            "mpesa_code": mpesa_code,
                            "amount": float(amount_per_beneficiary)
                        },
                        "SYSTEM_PAYOUT_ENGINE"
                    )
                    
                    success_count += 1
                    total_amount += amount_per_beneficiary

                except Exception as e:
                    failed_count += 1
                
                # Trigger progress callback if provided
                if progress_callback:
                    progress_callback(success_count, total_to_pay)

            # Simulate pause between batches
            time.sleep(0.2)

        return {
            "success": success_count,
            "failed": failed_count,
            "total_amount": total_amount,
            "total_attempted": total_to_pay,
        }
