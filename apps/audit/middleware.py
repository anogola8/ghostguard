"""Enterprise security middleware.

Adds HTTP security headers that Django doesn't send by default:
- Content-Security-Policy (CSP)
- Permissions-Policy
- Cross-Origin-Opener-Policy

These prevent XSS escalation, clickjacking, and data exfiltration
even if an attacker manages to inject HTML.
"""
from django.conf import settings


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy
        csp_parts = [
            f"default-src {settings.CSP_DEFAULT_SRC}",
            f"script-src {' '.join(settings.CSP_SCRIPT_SRC)}",
            f"style-src {' '.join(settings.CSP_STYLE_SRC)}",
            f"font-src {' '.join(settings.CSP_FONT_SRC)}",
            f"img-src {' '.join(settings.CSP_IMG_SRC)}",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "base-uri 'self'",
        ]
        response["Content-Security-Policy"] = "; ".join(csp_parts)

        # Permissions-Policy
        pp = ", ".join(f"{k}=({','.join(v)})" for k, v in settings.PERMISSIONS_POLICY.items())
        response["Permissions-Policy"] = pp

        # Cross-Origin isolation
        response["Cross-Origin-Opener-Policy"] = "same-origin"
        response["X-Frame-Options"] = "DENY"
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "same-origin"

        return response
