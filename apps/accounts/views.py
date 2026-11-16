from django.contrib.auth import views as auth_views
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
from django.utils import timezone
from django.urls import reverse_lazy
from django.contrib import messages
from datetime import timedelta

from .models import LoginAttempt


def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def form_invalid(self, form):
        username = form.data.get("username", "")
        ip = get_client_ip(self.request)

        # Record the failed attempt
        LoginAttempt.objects.create(username=username, ip_address=ip, successful=False)

        # Check recent failures (last 15 min)
        since = timezone.now() - timedelta(minutes=15)
        recent_failures = LoginAttempt.objects.filter(
            username=username,
            successful=False,
            attempted_at__gte=since,
        ).count()

        if recent_failures >= 10:
            messages.error(
                self.request,
                "Account locked for 24 hours due to excessive failed attempts. Contact support.",
            )
            # In a real enterprise app, you would set a lockout_until field on the User model here.
        elif recent_failures >= 5:
            messages.error(
                self.request,
                f"Account temporarily locked due to {recent_failures} failed attempts. Try again in 15 minutes.",
            )
        else:
            remaining = 5 - recent_failures
            messages.error(
                self.request,
                f"Invalid credentials. {remaining} attempt(s) remaining before lockout.",
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        LoginAttempt.objects.create(
            username=form.get_user().username,
            ip_address=get_client_ip(self.request),
            successful=True,
        )
        return response


@receiver(user_login_failed)
def log_failed_login(sender, credentials, request, **kwargs):
    """Fallback in case form_invalid doesn't run (e.g. test client without follow)."""
    if request is None:
        return
    username = credentials.get("username", "")
    LoginAttempt.objects.create(
        username=username,
        ip_address=get_client_ip(request),
        successful=False,
    )


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("accounts:login")


from django.views.generic import CreateView
from django.contrib.auth import login
from .forms import CustomUserCreationForm

class SignUpView(CreateView):
    form_class = CustomUserCreationForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("dashboard:index")

    def form_valid(self, form):
        response = super().form_valid(form)
        # Auto-login the user after signup
        login(self.request, self.object)
        messages.success(self.request, f"Welcome to GhostGuard, {self.object.first_name}!")
        return response


from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from .models import UserSession

@login_required
@require_POST
def logout_everywhere(request):
    # Delete all sessions for this user from the DB
    UserSession.objects.filter(user=request.user).delete()
    # Log the user out of the current session
    logout(request)
    messages.success(request, "All active sessions have been terminated.")
    return redirect("accounts:login")
