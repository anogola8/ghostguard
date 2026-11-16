import io
import base64

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, DetailView, View
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.db.models import Sum

from .models import Beneficiary, normalize_phone
from .forms import BeneficiaryForm
from apps.audit.services import append
from apps.audit.models import EventType
from apps.detection.engine import detect_duplicates
from apps.programs.models import Payout


class RegisterBeneficiaryView(LoginRequiredMixin, CreateView):
    model = Beneficiary
    form_class = BeneficiaryForm
    template_name = "beneficiaries/register.html"
    success_url = reverse_lazy("beneficiaries:register")

    def form_valid(self, form):
        form.instance.registered_by = self.request.user
        flags = detect_duplicates(
            new_name=form.cleaned_data["full_name"],
            new_phone=form.cleaned_data["phone"],
            new_id_hash=form.instance.id_reference_hash,
            program_id=form.cleaned_data["program"].id,
        )
        if flags:
            form.instance.detection_flags = flags
            if any(f["layer"] == "EXACT" for f in flags):
                form.instance.status = Beneficiary.Status.FLAGGED
                messages.warning(self.request, "Exact duplicate detected. Beneficiary flagged for review.")
            else:
                messages.info(self.request, "Potential duplicate detected. Record saved with flags.")

        response = super().form_valid(form)
        append(
            EventType.BENEFICIARY_REGISTERED,
            payload={
                "beneficiary_id": self.object.pk,
                "public_id": self.object.public_id,
                "name": self.object.full_name,
                "program_id": self.object.program_id,
                "flags_count": len(flags),
            },
            actor_username=self.request.user.get_username(),
        )
        messages.success(self.request, f"Beneficiary {self.object.full_name} registered. ID: {self.object.public_id}")
        return response


class PublicBeneficiaryCardView(DetailView):
    model = Beneficiary
    template_name = "beneficiaries/public_card.html"
    context_object_name = "beneficiary"

    def get_object(self, queryset=None):
        return get_object_or_404(Beneficiary, public_id=self.kwargs["public_id"])

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        b = self.object

        # Total paid to this beneficiary
        total = Payout.objects.filter(beneficiary=b).aggregate(Sum("amount"))["amount__sum"] or 0
        ctx["total_paid"] = total

        # All payouts (for the mini ledger)
        ctx["payouts"] = Payout.objects.filter(beneficiary=b).select_related("round__program").order_by("-paid_at")[:10]

        # Generate a QR code pointing to this page
        try:
            import qrcode
            url = self.request.build_absolute_uri(reverse("beneficiaries:public_card", kwargs={"public_id": b.public_id}))
            qr = qrcode.QRCode(version=1, box_size=6, border=2)
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            ctx["qr_data_url"] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as e:
            ctx["qr_data_url"] = None
            ctx["qr_error"] = str(e)

        return ctx


class PayoutReceiptView(DetailView):
    """A printable receipt for a single payout."""
    from apps.programs.models import Payout as _Payout
    model = _Payout
    template_name = "beneficiaries/payout_receipt.html"
    context_object_name = "payout"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Deterministic receipt hash so the beneficiary can compare
        import hashlib
        p = self.object
        raw = f"{p.id}|{p.beneficiary.public_id}|{p.amount}|{p.paid_at.isoformat()}"
        ctx["receipt_hash"] = hashlib.sha256(raw.encode()).hexdigest()
        return ctx


class BulkUploadView(LoginRequiredMixin, View):
    template_name = "beneficiaries/bulk_upload.html"

    def get(self, request):
        from apps.programs.models import Program
        return render(request, self.template_name, {"programs": Program.objects.all()})

    def post(self, request):
        import csv
        from io import TextIOWrapper
        from apps.programs.models import Program
        
        csv_file = request.FILES.get("csv_file")
        program_id = request.POST.get("program")

        if not csv_file or not program_id:
            messages.error(request, "Please select a program and upload a CSV.")
            return redirect("beneficiaries:bulk_upload")

        program = get_object_or_404(Program, pk=program_id)
        
        try:
            decoded_file = TextIOWrapper(csv_file.file, encoding="utf-8")
            reader = csv.DictReader(decoded_file)
            
            success_count = 0
            flag_count = 0
            
            for row in reader:
                name = row.get("full_name", "").strip()
                phone = row.get("phone", "").strip()
                village = row.get("village", "").strip()
                id_ref = row.get("id_reference", "").strip()

                if not name or not phone:
                    continue

                b = Beneficiary(
                    program=program, full_name=name, phone=normalize_phone(phone),
                    village=village, registered_by=request.user
                )
                if id_ref:
                    b.set_id_reference(id_ref)

                # Run detection
                flags = detect_duplicates(
                    new_name=name, new_phone=b.phone,
                    new_id_hash=b.id_reference_hash, program_id=program.id
                )
                if flags:
                    b.detection_flags = flags
                    if any(f["layer"] == "EXACT" for f in flags):
                        b.status = Beneficiary.Status.FLAGGED
                        flag_count += 1
                
                # Generate public ID
                import secrets
                import datetime
                year = datetime.datetime.now().strftime("%y")
                b.public_id = f"GG-{year}-{secrets.token_hex(2).upper()}"
                
                b.save()
                success_count += 1

            messages.success(request, f"Successfully processed {success_count} records. ({flag_count} auto-flagged for review).")
            return redirect("dashboard:directory")
            
        except Exception as e:
            messages.error(request, f"Error processing CSV: {str(e)}")
            return redirect("beneficiaries:bulk_upload")
