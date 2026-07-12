"""Main Django Ninja API instance — all routers are mounted here."""
from ninja import NinjaAPI
from ninja.errors import HttpError

from .security import AuthBearer

api = NinjaAPI(
    title="Ochre ERP API",
    version="1",
    description=(
        "Auto-generated REST API for all Ochre ERP entities. "
        "Every entity defined via the metadata engine is available here."
    ),
    auth=AuthBearer(),
    urls_namespace="ochre_api",
)

# --- Core routers ---
from core.auth.api import router as auth_router  # noqa: E402
api.add_router("/auth", auth_router)


# --- Global error handlers ---
@api.exception_handler(HttpError)
def http_error_handler(request, exc: HttpError):
    return api.create_response(request, {"detail": exc.message}, status=exc.status_code)
