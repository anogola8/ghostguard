from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"

    def ready(self) -> None:
        from . import guards  # noqa: F401  (register signal receivers)
