from fastapi import APIRouter
from typing import List

from src.api.locales import active_locales
from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.config import settings

router = APIRouter(tags=["overrides"])
_bc = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
_srv = ProductLocalizationService(_bc)


@router.get("/overrides")
async def list_overrides(ids: str | None = None, channel_id: int = settings.BC_CHANNEL_ID):
    if ids:
        prod_ids: List[int] = [int(x) for x in ids.split(",") if x]
    else:
        prod_ids = [p["id"] for p in _srv.bc.rest("/catalog/products", params={"limit": 10}).get("data", [])]

    locales = active_locales(channel_id)
    rows = []
    for pid in prod_ids:
        data = _srv.get_localized_data(pid, channel_id, locales)
        for loc, payload in data.items():
            rows.append({"id": pid, "locale": loc, "name": payload["name"], "description": payload["description"]})
    return rows

