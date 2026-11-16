from django.contrib.auth import logout
from django.shortcuts import redirect
from django.contrib import messages
from .models import UserSession


class SessionSecurityMiddleware:
    """Binds sessions to IP + User-Agent and tracks active sessions."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            session_key = request.session.session_key
            if not session_key:
                request.session.save()
                session_key = request.session.session_key

            user_agent = request.META.get("HTTP_USER_AGENT", "")
            ip_address = request.META.get("REMOTE_ADDR")

            # 1. Track the session (create or update)
            session, created = UserSession.objects.get_or_create(
                session_key=session_key,
                defaults={"user": request.user, "ip_address": ip_address, "user_agent": user_agent}
            )

            if not created:
                # 2. Detect Session Hijacking
                if session.user_agent != user_agent:
                    from apps.audit.services import log_attack
                    log_attack(
                        request,
                        attack_type="SESSION_HIJACK",
                        payload={
                            "expected_ua": session.user_agent[:100],
                            "actual_ua": user_agent[:100],
                            "session_key": session_key[:8],
                        },
                        blocked=True,
                    )
                    logout(request)
                    messages.error(request, "Security Alert: Session invalidated due to browser mismatch. Please log in again.")
                    return redirect("accounts:login")
                
                # Update last activity
                session.save() # auto_now updates last_activity

        response = self.get_response(request)
        return response
