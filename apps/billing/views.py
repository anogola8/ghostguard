from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import redirect
from apps.accounts.models import Organization
from apps.audit.models import AuditEntry
from apps.audit.services import verify_integrity

class PricingView(TemplateView):
    template_name = "billing/pricing.html"

class UpgradeView(LoginRequiredMixin, TemplateView):
    template_name = "billing/upgrade.html"

    def post(self, request, *args, **kwargs):
        tier = request.POST.get("tier", "PRO")
        org, _ = Organization.objects.get_or_create(name=f"{request.user.username} Org")
        org.tier = tier
        org.save()
        request.user.organization = org
        request.user.save()
        messages.success(request, f"Successfully upgraded to {tier} plan! Your new limits are active.")
        return redirect("dashboard:index")

def donor_api_audit(request, api_key):
    """External API for Donors to pull the verified audit log."""
    try:
        org = Organization.objects.get(api_key=api_key)
    except Organization.DoesNotExist:
        from apps.audit.services import log_attack
        log_attack(
            request,
            attack_type="API_ENUM",
            payload={"attempted_key_prefix": api_key[:8] if api_key else ""},
            blocked=True,
        )
        return JsonResponse({"error": "Invalid API Key"}, status=401)

    # Verify chain before returning data
    result = verify_integrity()
    if not result.ok:
        return JsonResponse({"error": "Chain integrity failed", "sequence": result.first_broken_sequence}, status=500)

    # Fetch recent audit entries for this org
    entries = AuditEntry.objects.all().order_by("-sequence")[:50]
    data = []
    for e in entries:
        data.append({
            "sequence": e.sequence,
            "event": e.event_type,
            "actor": e.actor_username,
            "payload": e.payload,
            "hash": e.entry_hash,
            "timestamp": e.created_at.isoformat()
        })

    return JsonResponse({
        "organization": org.name,
        "tier": org.tier,
        "chain_status": "INTACT",
        "total_entries": result.entries_checked,
        "recent_entries": data
    })
