import json
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import TemplateView, ListView, DetailView
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Count, Sum, Q
from django.http import HttpResponse
from django.contrib import messages
from django.utils import timezone

from apps.programs.models import Program, DisbursementRound, Payout
from apps.beneficiaries.models import Beneficiary
from apps.audit.models import AuditEntry, EventType
from apps.audit.services import verify_integrity, append


class DonorDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        programs = Program.objects.annotate(
            b_count=Count("beneficiaries", distinct=True),
            p_paid=Sum("rounds__payouts__amount", distinct=True),
        )
        beneficiaries = Beneficiary.objects.all()
        flagged = beneficiaries.filter(status=Beneficiary.Status.FLAGGED).count()
        total = beneficiaries.count()
        total_paid = Payout.objects.aggregate(Sum("amount"))["amount__sum"] or 0

        for p in programs:
            p.beneficiary_count = p.b_count
            p.total_paid = p.p_paid
        ctx["programs"] = programs
        ctx["total_beneficiaries"] = total
        ctx["flagged_beneficiaries"] = flagged
        ctx["total_audit_entries"] = AuditEntry.objects.count()
        ctx["total_paid"] = total_paid
        ctx["recent_activity"] = AuditEntry.objects.order_by("-sequence")[:5]

        chart_labels = [p.name for p in programs]
        chart_data = [
            Beneficiary.objects.filter(program=p, status=Beneficiary.Status.FLAGGED).count()
            for p in programs
        ]
        ctx["chart_labels"] = json.dumps(chart_labels)
        ctx["chart_data"] = json.dumps(chart_data)
        return ctx


class FlagQueueView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Beneficiary
    template_name = "dashboard/flag_queue.html"
    context_object_name = "flagged"

    def test_func(self):
        return self.request.user.role in ["PROGRAM_MANAGER", "SYSTEM_ADMIN"]

    def get_queryset(self):
        return Beneficiary.objects.filter(status=Beneficiary.Status.FLAGGED).order_by("-registered_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        enriched_flagged = []
        for b in ctx["flagged"]:
            enriched_flags = []
            for flag in b.detection_flags:
                matched_id = flag.get("matched_id")
                matched_record = None
                if matched_id:
                    try:
                        matched_record = Beneficiary.objects.get(id=matched_id)
                    except Beneficiary.DoesNotExist:
                        pass
                enriched_flags.append({
                    "raw": flag,
                    "matched_record": matched_record,
                })
            b.enriched_flags = enriched_flags
            enriched_flagged.append(b)
        ctx["flagged"] = enriched_flagged
        return ctx

    def post(self, request, *args, **kwargs):
        beneficiary_id = request.POST.get("beneficiary_id")
        action = request.POST.get("action")
        if not beneficiary_id or action not in ["RESOLVE", "DISMISS"]:
            return redirect("dashboard:flag_queue")
        b = get_object_or_404(Beneficiary, pk=beneficiary_id)
        if action == "RESOLVE":
            b.status = Beneficiary.Status.ACTIVE
            b.detection_flags = []
            b.save()
            append(EventType.FLAG_RESOLVED, {"beneficiary_id": b.id, "action": "Resolved as clear"}, request.user.username)
            messages.success(request, f"Record for {b.full_name} marked as clear.")
        else:
            b.status = Beneficiary.Status.INACTIVE
            b.save()
            append(EventType.FLAG_RESOLVED, {"beneficiary_id": b.id, "action": "Blocked as fraud"}, request.user.username)
            messages.warning(request, f"Record for {b.full_name} blocked.")
        return redirect("dashboard:flag_queue")


class BeneficiaryDirectoryView(LoginRequiredMixin, ListView):
    model = Beneficiary
    template_name = "dashboard/directory.html"
    context_object_name = "beneficiaries"
    paginate_by = 20

    def get_queryset(self):
        qs = Beneficiary.objects.all().order_by("-registered_at")
        if self.request.user.role == "FIELD_OFFICER":
            qs = qs.filter(registered_by=self.request.user)
        q = self.request.GET.get("q")
        if q:
            qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q))
        return qs


class PDFReportView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/report.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["programs"] = Program.objects.annotate(
            beneficiary_count=Count("beneficiaries"),
            flagged_count=Count("beneficiaries", filter=Q(beneficiaries__status="FLAGGED")),
            total_paid=Sum("rounds__payouts__amount"),
        )
        ctx["verify_result"] = verify_integrity()
        ctx["recent_audit"] = AuditEntry.objects.order_by("-sequence")[:20]
        return ctx


def download_pdf(request):
    """Generate the audit report as a PDF using ReportLab (no native deps)."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm,
        title="GhostGuard Audit Report")
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=20, textColor=colors.HexColor("#1f2937"))
    sub = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, textColor=colors.HexColor("#4b5563"), spaceBefore=14)
    body = styles["BodyText"]

    story = [
        Paragraph("GhostGuard Audit Report", heading),
        Paragraph("Generated by <b>" + request.user.username + "</b> at " + timezone.now().strftime("%Y-%m-%d %H:%M"), body),
        Spacer(1, 8*mm),
    ]

    result = verify_integrity()
    story.append(Paragraph("Chain Integrity", sub))
    if result.ok:
        status = "<font color='#059669'><b>INTACT</b></font> - " + str(result.entries_checked) + " entries verified."
    else:
        status = "<font color='#dc2626'><b>TAMPERED</b></font> - first broken at sequence " + str(result.first_broken_sequence) + "."
    story.append(Paragraph(status, body))
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph("Programs Summary", sub))
    programs = Program.objects.annotate(
        beneficiary_count=Count("beneficiaries"),
        flagged_count=Count("beneficiaries", filter=Q(beneficiaries__status="FLAGGED")),
        total_paid=Sum("rounds__payouts__amount"),
    )
    rows = [["Program", "Beneficiaries", "Flagged", "Total Paid (KSh)"]]
    for p in programs:
        rows.append([p.name, str(p.beneficiary_count), str(p.flagged_count), "{:,.2f}".format(p.total_paid or 0)])
    if len(rows) == 1:
        rows.append(["(no programs)", "-", "-", "-"])
    tbl = Table(rows, colWidths=[70*mm, 30*mm, 25*mm, 40*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e5e7eb")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#d1d5db")),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6*mm))

    story.append(Paragraph("Recent Audit Trail", sub))
    audit_rows = [["#", "Event", "Actor", "Hash", "Time"]]
    for e in AuditEntry.objects.order_by("-sequence")[:20]:
        audit_rows.append([str(e.sequence), e.get_event_type_display(), e.actor_username or "-",
                          e.entry_hash[:16], e.created_at.strftime("%Y-%m-%d %H:%M")])
    atbl = Table(audit_rows, colWidths=[12*mm, 55*mm, 30*mm, 40*mm, 28*mm])
    atbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e5e7eb")),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7.5),
        ("GRID", (0,0), (-1,-1), 0.3, colors.HexColor("#d1d5db")),
    ]))
    story.append(atbl)

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = "attachment; filename=ghostguard_audit_report.pdf"
    resp["Content-Length"] = len(pdf_bytes)
    return resp


class PublicTransparencyView(TemplateView):
    template_name = "dashboard/public.html"

    def mask_name(self, name):
        if not name:
            return "Unknown"
        parts = name.split()
        if len(parts) == 1:
            return parts[0][:3] + "***"
        return parts[0] + " " + parts[-1][0] + "***"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        programs = Program.objects.annotate(
            b_count=Count("beneficiaries", distinct=True),
            p_paid=Sum("rounds__payouts__amount", distinct=True),
        )
        recent_payouts = Payout.objects.select_related(
            "beneficiary", "round__program"
        ).order_by("-paid_at")[:15]
        ledger_entries = []
        for p in recent_payouts:
            ledger_entries.append({
                "name": self.mask_name(p.beneficiary.full_name),
                "village": p.beneficiary.village or "Unknown",
                "program": p.round.program.name,
                "amount": p.amount,
                "date": p.paid_at,
                "reference": p.reference,
            })
        for p in programs:
            p.beneficiary_count = p.b_count
            p.total_paid = p.p_paid
        ctx["programs"] = programs
        ctx["ledger_entries"] = ledger_entries
        ctx["verify_result"] = verify_integrity()
        ctx["total_paid_all"] = Payout.objects.aggregate(Sum("amount"))["amount__sum"] or 0
        return ctx


class DisputeQueueView(LoginRequiredMixin, ListView):
    model = __import__("apps.beneficiaries.models", fromlist=["Dispute"]).Dispute
    template_name = "dashboard/disputes.html"
    context_object_name = "disputes"

    def get_queryset(self):
        from apps.beneficiaries.models import Dispute
        return Dispute.objects.filter(status=Dispute.Status.OPEN).order_by("-created_at")

    def post(self, request, *args, **kwargs):
        from apps.beneficiaries.models import Dispute, Beneficiary
        dispute_id = request.POST.get("dispute_id")
        action = request.POST.get("action")
        
        if not dispute_id or action not in ["CLEAR", "CONFIRM_FRAUD"]:
            return redirect("dashboard:disputes")

        dispute = get_object_or_404(__import__("apps.beneficiaries.models", fromlist=["Dispute"]).Dispute, pk=dispute_id)
        
        if action == "CLEAR":
            dispute.status = dispute.Status.RESOLVED
            dispute.beneficiary.status = Beneficiary.Status.ACTIVE
            dispute.beneficiary.detection_flags = []
            dispute.beneficiary.save()
            messages.success(request, "Dispute resolved. Beneficiary cleared.")
            append(EventType.FLAG_RESOLVED, {"dispute_id": dispute.id, "action": "Cleared via Dispute"}, request.user.username)
        else:
            dispute.status = dispute.Status.REJECTED
            messages.warning(request, "Dispute rejected. Fraud confirmed.")
            append(EventType.FLAG_RESOLVED, {"dispute_id": dispute.id, "action": "Fraud Confirmed via Dispute"}, request.user.username)
        
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save()
        
        return redirect("dashboard:disputes")


from django.contrib.auth.mixins import UserPassesTestMixin
from apps.audit.models import SystemSettings

class SystemSettingsView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "dashboard/settings.html"

    def test_func(self):
        return self.request.user.role == "SYSTEM_ADMIN"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["settings"] = SystemSettings.get_settings()
        return ctx

    def post(self, request):
        threshold = request.POST.get("fuzzy_threshold")
        if threshold:
            settings_obj = SystemSettings.get_settings()
            settings_obj.fuzzy_threshold = float(threshold)
            settings_obj.save()
            append(EventType.USER_ROLE_CHANGED, {"action": "Settings updated", "threshold": threshold}, request.user.username)
            messages.success(request, f"System threshold updated to {float(threshold)*100:.0f}%")
        return redirect("dashboard:settings")



class SecurityDashboardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "dashboard/security.html"

    def test_func(self):
        return self.request.user.role == "SYSTEM_ADMIN"

    def get_context_data(self, **kwargs):
        from datetime import timedelta
        from apps.accounts.models import LoginAttempt

        ctx = super().get_context_data(**kwargs)
        since = timezone.now() - timedelta(hours=24)

        attempts = LoginAttempt.objects.filter(attempted_at__gte=since)
        failed = attempts.filter(successful=False)
        successful = attempts.filter(successful=True)

        # Group failures by username to find locked accounts
        from django.db.models import Count
        locks = (
            failed.values("username")
            .annotate(count=Count("id"))
            .filter(count__gte=5)
            .order_by("-count")
        )

        ctx["failed_24h"] = failed.count()
        ctx["successful_24h"] = successful.count()
        ctx["locked_accounts"] = locks
        ctx["recent_failures"] = failed.order_by("-attempted_at")[:20]
        ctx["recent_logins"] = successful.order_by("-attempted_at")[:10]
        
        from apps.accounts.models import UserSession
        ctx["active_sessions"] = UserSession.objects.filter(user=self.request.user).order_by("-last_activity")
        ctx["password_warning"] = (self.request.user.username == "dero" and self.request.user.check_password("testpass123"))

        return ctx


class AttackLogView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "dashboard/attack_log.html"

    def test_func(self):
        return self.request.user.role == "SYSTEM_ADMIN"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from apps.audit.models import AttackLog
        from django.db.models import Count
        from datetime import timedelta

        logs = AttackLog.objects.all()
        ctx["logs"] = logs[:100]  # Latest 100

        # Summary stats
        since = timezone.now() - timedelta(hours=24)
        last_24h = logs.filter(created_at__gte=since)
        ctx["total_attacks_24h"] = last_24h.count()
        ctx["unique_ips"] = last_24h.values("ip_address").distinct().count()

        # Top attack types
        from collections import Counter
        type_counts = last_24h.values("attack_type").annotate(count=Count("id")).order_by("-count")[:5]
        ctx["attack_types"] = type_counts

        # Top attacking IPs
        ctx["top_ips"] = last_24h.exclude(ip_address__isnull=True).values("ip_address").annotate(count=Count("id")).order_by("-count")[:5]

        return ctx
