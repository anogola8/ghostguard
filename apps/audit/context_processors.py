def system_health(request):
    try:
        from .models import SystemHealth
        return {"system_health": SystemHealth.get_health()}
    except Exception:
        return {"system_health": None}
