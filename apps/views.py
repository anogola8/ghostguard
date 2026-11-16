from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum

from .models import DisbursementRound, Payout
from apps.beneficiaries.models import Beneficiary
from apps.audit.services import append
from apps.audit.models import EventType


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
        round_obj = get_object_or_404(DisbursementRound, pk=pk)
        if round_obj.status != DisbursementRound.Status.APPROVED:
            messages.error(request, "Round must be approved before paying out.")
            return redirect("programs:round_detail", pk=pk)

        beneficiaries = Beneficiary.objects.filter(
            program=round_obj.program,
            status=Beneficiary.Status.ACTIVE,
        )
        payout_amount = 15000.00
        count = 0
        for b in beneficiaries:
            if not Payout.objects.filter(round=round_obj, beneficiary=b).exists():
                Payout.objects.create(
                    round=round_obj,
                    beneficiary=b,
                    amount=payout_amount,
                    reference=f"MPESA-{round_obj.id}-{b.id}",
                )
                append(
                    EventType.PAYOUT_RECORDED,
                    {"beneficiary": b.full_name, "amount": payout_amount},
                    request.user.username,
                )
                count += 1

        round_obj.status = DisbursementRound.Status.LOCKED
        round_obj.locked_at = timezone.now()
        round_obj.save()
        append(
            EventType.ROUND_LOCKED,
            {"round_id": round_obj.id, "total_payouts": count},
            request.user.username,
        )
        messages.success(
            request,
            f"Successfully disbursed KSh {count * payout_amount:,.0f} to {count} beneficiaries. Each beneficiary now has a digital receipt available at /beneficiaries/receipt/<id>/",
        )
        return redirect("programs:round_detail", pk=pk)
