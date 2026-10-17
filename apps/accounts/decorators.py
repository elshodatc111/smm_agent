from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponseForbidden, JsonResponse

from .permissions_registry import GLOBAL_MODULES, validate
from .services import perms


def require_permission(code: str):
    """View dekoratori. Biznesga bog'liq modullar uchun request.business shart (server tomonda)."""
    validate(code)
    module = code.split(".")[0]

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.path.startswith("/api/"):
                    return JsonResponse({"error": {"code": "not_authenticated", "message_uz": "Avval tizimga kiring."}}, status=401)
                return redirect_to_login(request.get_full_path())
            biz = getattr(request, "business", None)
            if request.user.is_admin and request.user.is_active:
                return view(request, *args, **kwargs)   # admin: hali biznes bo'lmasa ham kira oladi
            if module not in GLOBAL_MODULES:
                if biz is None:
                    # «Barcha bizneslar» ko'rinishi: kamida bitta biznesda ruxsat bo'lishi kerak
                    if not perms.businesses_for(request.user, code).exists():
                        return _deny(request)
                elif not perms.has_business(request.user, biz.pk):
                    raise Http404
            if not perms.can(request.user, code, biz) and not (
                    biz is None and module not in GLOBAL_MODULES and perms.businesses_for(request.user, code).exists()):
                return _deny(request)
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def _deny(request):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": {"code": "permission_denied", "message_uz": "Bu amalga ruxsat yo'q."}}, status=403)
    from apps.web.views_core import permission_denied
    return permission_denied(request)
