from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum

from .models import DisbursementRound, Payout
from apps.beneficiaries.models import Beneficiary
from apps.audit.services import append
from apps.audit.models import EventType, SystemHealth
from .services import PayoutEngine


class RoundListView(LoginRequiredMixin, ListView):
    model = DisbursementRound
    template_name = "programs/round_list.html"
    context_object_name = "rounds"


class RoundDetailView(LoginRequiredMixin, DetailView):
    model = DisbursementRound
    template_name = "programs/round_detail.html"
    context_object_name = "round"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        total = Payout.objects.filter(round=self.object).aggregate(
            Sum("amount")
        )["amount__sum"] or 0
        ctx["total_paid"] = total
        ctx["active_count"] = Beneficiary.objects.filter(
            program=self.object.program,
            status=Beneficiary.Status.ACTIVE,
        ).count()
        return ctx


class LockRoundView(LoginRequiredMixin, View):
    def post(self, request, pk):
        health = SystemHealth.get_health()
        if health.status == SystemHealth.Status.QUARANTINED:
            messages.error(request, f"System is in QUARANTINE due to tamper detection at sequence {health.tamper_sequence}. Contact your administrator.")
            return redirect("programs:round_detail", pk=pk)

        round_obj = get_object_or_404(DisbursementRound, pk=pk)
        if round_obj.status == DisbursementRound.Status.DRAFT:
            round_obj.status = DisbursementRound.Status.APPROVED
            round_obj.approved_at = timezone.now()
            round_obj.save()
            append(
                EventType.ROUND_APPROVED,
                {"round_id": round_obj.id},
                request.user.username,
            )
            messages.success(request, "Round approved. Ready to disburse funds.")
        elif round_obj.status == DisbursementRound.Status.APPROVED:
            round_obj.status = DisbursementRound.Status.LOCKED
            round_obj.locked_at = timezone.now()
            round_obj.save()
            append(
                EventType.ROUND_LOCKED,
                {"round_id": round_obj.id},
                request.user.username,
            )
            messages.success(request, "Round locked. No further edits allowed.")
        return redirect("programs:round_detail", pk=pk)


class ProcessPayoutsView(LoginRequiredMixin, View):
    def post(self, request, pk):
        health = SystemHealth.get_health()
        if health.status == SystemHealth.Status.QUARANTINED:
            messages.error(request, f"System is in QUARANTINE due to tamper detection at sequence {health.tamper_sequence}. No funds will be disbursed. Contact your administrator.")
            return redirect("programs:round_detail", pk=pk)

        round_obj = get_object_or_404(DisbursementRound, pk=pk)
        if round_obj.status != DisbursementRound.Status.APPROVED:
            messages.error(request, "Round must be approved before paying out.")
            return redirect("programs:round_detail", pk=pk)

        # Initialize the engine
        engine = PayoutEngine(round_obj)
        
        # Execute the batch payout
        result = engine.execute(amount_per_beneficiary=15000.00)
        
        # Lock the round
        round_obj.status = DisbursementRound.Status.LOCKED
        round_obj.locked_at = timezone.now()
        round_obj.save()
        
        append(
            EventType.ROUND_LOCKED,
            {
                "round_id": round_obj.id, 
                "total_payouts": result["success"],
                "total_failed": result["failed"]
            },
            request.user.username,
        )
        
        messages.success(
            request,
            f"Autonomous Payout Complete: Disbursed KSh {result['total_amount']:,.0f} to {result['success']} beneficiaries.",
        )
        return redirect("programs:round_detail", pk=pk)
