from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            exc = DRFValidationError(exc.message_dict)
        else:
            exc = DRFValidationError(exc.messages)

    response = exception_handler(exc, context)
    if response is None:
        return None
    details = response.data
    message = details.get("detail") if isinstance(details, dict) else None
    response.data = {
        "error": {
            "status": response.status_code,
            "message": str(message or "Richiesta non valida."),
            "details": details,
        }
    }
    return response
