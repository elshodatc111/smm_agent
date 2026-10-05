from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler


def exception_handler(exc, context):
    resp = drf_handler(exc, context)
    if resp is None:
        return None
    code = {400: "validation_error", 401: "not_authenticated", 403: "permission_denied",
            404: "not_found", 409: "invalid_state_transition", 422: "rule_blocked", 429: "rate_limited"
            }.get(resp.status_code, "error")
    detail = resp.data.get("detail") if isinstance(resp.data, dict) else None
    msgs = {"permission_denied": "Bu amalga ruxsat yo'q.", "not_found": "Topilmadi.",
            "not_authenticated": "Avval tizimga kiring."}
    return Response({"error": {"code": code, "message_uz": msgs.get(code, str(detail or "Xatolik")),
                               "details": resp.data}}, status=resp.status_code)
