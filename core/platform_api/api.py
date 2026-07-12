"""Main Django Ninja API instance — all routers are mounted here."""
from ninja import NinjaAPI
from ninja.errors import HttpError

from .security import AuthBearer

api = NinjaAPI(
    title="Odum ERP Suite API",
    version="1",
    description=(
        "Auto-generated REST API for all Odum ERP Suite entities. "
        "Every entity defined via the metadata engine is available here."
    ),
    auth=AuthBearer(),
    urls_namespace="ochre_api",
)

# --- Core routers ---
from core.auth.api import router as auth_router  # noqa: E402
api.add_router("/auth", auth_router)

# --- Phase 1 business app action routers ---
from apps.accounting.api import router as accounting_router  # noqa: E402
from apps.crm.api import router as crm_router  # noqa: E402
from apps.purchasing.api import router as purchasing_router  # noqa: E402
from apps.sales.api import router as sales_router  # noqa: E402
from apps.manufacturing.api import router as manufacturing_router  # noqa: E402
from apps.pos.api import router as pos_router  # noqa: E402

api.add_router("/accounting", accounting_router)
api.add_router("/crm", crm_router)
api.add_router("/purchasing", purchasing_router)
api.add_router("/sales", sales_router)
api.add_router("/manufacturing", manufacturing_router)
api.add_router("/pos", pos_router)

# --- Phase 4 industry app action routers ---
from apps.education_sis.api import router as education_sis_router  # noqa: E402
from apps.healthcare_his.api import router as healthcare_his_router  # noqa: E402
from apps.agriculture.api import router as agriculture_router  # noqa: E402
from apps.nonprofit.api import router as nonprofit_router  # noqa: E402
from apps.telecom.api import router as telecom_router  # noqa: E402
from apps.government.api import router as government_router  # noqa: E402
from apps.microfinance.api import router as microfinance_router  # noqa: E402
from apps.legal_services.api import router as legal_services_router  # noqa: E402

api.add_router("/education", education_sis_router)
api.add_router("/healthcare", healthcare_his_router)
api.add_router("/agriculture", agriculture_router)
api.add_router("/nonprofit", nonprofit_router)
api.add_router("/telecom", telecom_router)
api.add_router("/government", government_router)
api.add_router("/microfinance", microfinance_router)
api.add_router("/legal", legal_services_router)


from core.platform_api.meta import meta_router  # noqa: E402
api.add_router("/meta", meta_router)


# --- Global error handlers ---
@api.exception_handler(HttpError)
def http_error_handler(request, exc: HttpError):
    return api.create_response(request, {"detail": exc.message}, status=exc.status_code)
