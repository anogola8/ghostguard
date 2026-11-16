from django.shortcuts import redirect
from django.contrib import messages
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

from .models import AuditEntry, EventType
from .services import append, verify_integrity


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["entry_count"] = AuditEntry.objects.count()
        ctx["result"] = verify_integrity() if self.request.user.is_authenticated else None
        return ctx


class IntegrityCheckView(LoginRequiredMixin, View):
    template_name = "audit/integrity.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {"result": None, "recent": AuditEntry.objects.order_by("-sequence")[:10]},
        )

    def post(self, request):
        result = verify_integrity()
        append(
            EventType.INTEGRITY_CHECKED,
            payload={
                "ok": result.ok,
                "first_broken_sequence": result.first_broken_sequence,
                "entries_checked": result.entries_checked,
            },
            actor_username=request.user.get_username(),
        )
        return render(
            request,
            self.template_name,
            {"result": result, "recent": AuditEntry.objects.order_by("-sequence")[:10]},
        )


from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from .models import SystemHealth, AuditEntry, EventType
from .services import append
import json

@login_required
@require_POST
def acknowledge_tamper(request):
    if request.user.role != "SYSTEM_ADMIN":
        return HttpResponseForbidden("Only System Administrators can acknowledge a tamper.")

    phrase = request.POST.get("confirm_phrase", "").strip()
    if phrase != "I ACKNOWLEDGE THE TAMPER":
        messages.error(request, "Incorrect confirmation phrase. You must type exactly: I ACKNOWLEDGE THE TAMPER")
        return redirect("dashboard:security")

    health = SystemHealth.get_health()
    if health.status != SystemHealth.Status.QUARANTINED:
        messages.info(request, "System is not in quarantine.")
        return redirect("dashboard:security")

    # Capture the tamper details before wiping
    tamper_seq = health.tamper_sequence
    tamper_reason = health.tamper_reason

    # Wipe the broken chain via raw SQL (sanctioned admin action)
    # The ORM guard blocks .delete() by design; raw SQL bypasses it for this verified case.
    from django.db import connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM audit_auditentry")

    # Reset health
    health.status = SystemHealth.Status.HEALTHY
    health.tamper_sequence = None
    health.tamper_reason = ""
    health.detected_at = None
    health.acknowledged_by = request.user.username
    health.save()

    # Start a new chain with a documented restoration event
    append(
        EventType.USER_ROLE_CHANGED,
        {
            "action": "TAMPER ACKNOWLEDGED & SYSTEM RESTORED",
            "acknowledged_by": request.user.username,
            "original_tamper_sequence": tamper_seq,
            "original_tamper_reason": tamper_reason,
        },
        actor_username=request.user.username,
    )

    messages.success(request, "Tamper acknowledged. Chain wiped. New genesis entry created to document the incident.")
    return redirect("dashboard:security")
