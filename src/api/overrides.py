from fastapi import APIRouter
from typing import List

from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.services.query_processors import process_gql_locales
from src.queries.gql_locale_queries import get_locales
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

    locales = _active_locales(channel_id)
    rows = []
    for pid in prod_ids:
        data = _srv.get_localized_data(pid, channel_id, locales)
        for loc, payload in data.items():
            rows.append({"id": pid, "locale": loc, "name": payload["name"], "description": payload["description"]})
    return rows


def _active_locales(channel_id: int):
    q, variables = get_locales(channel_id)
    resp = _bc.graphql(q, variables=variables, admin=True)
    return [c for c, meta in process_gql_locales(resp).items() if meta.get("status") == "ACTIVE"]