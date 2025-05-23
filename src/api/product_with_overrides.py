# src/api/products_with_overrides.py
from typing import List, Dict, Any
from fastapi import APIRouter, Query
from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.queries.gql_locale_queries import get_locales
from src.services.query_processors import process_gql_locales
from src.queries.gql_multilang_queries import get_product_query, get_update_mutation
from src.config import settings

router = APIRouter(tags=["overrides"])

_bc  = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
_srv = ProductLocalizationService(_bc)


def _active_locales(channel_id: int) -> List[str]:
    q, v = get_locales(channel_id)
    resp = _bc.graphql(q, variables=v, admin=True)
    return [
        loc for loc, meta in process_gql_locales(resp).items()
        if meta.get("status") == "ACTIVE"
    ]


@router.get("/products-with-overrides")
async def products_with_overrides(
    ids: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    channel_id: int = settings.BC_CHANNEL_ID,
):
    if ids:
        product_ids = [int(x) for x in ids.split(",") if x]
    else:
        offs, lim = (page - 1) * limit, limit
        base = _bc.rest(
            "/catalog/products", params={"limit": lim, "page": page}
        ).get("data", [])
        product_ids = [p["id"] for p in base]

    locales = _active_locales(channel_id)
    gql     = get_product_query()
    results: List[Dict[str, Any]] = []

    for pid in product_ids:
        per_locale = []
        for loc in locales:
            vars_ = {
                "productId": f"bc/store/product/{pid}",
                "channelId": f"bc/store/channel/{channel_id}",
                "locale": loc,
            }
            data = _bc.graphql(gql, variables=vars_, admin=True) or {}
            node = (
                data.get("data", {})
                .get("store", {})
                .get("products", {})
                .get("edges", [])
            )
            if not node:
                continue
            node = node[0].get("node", {}) or {}
            base_info = node.get("basicInformation") or {}
            override = node.get("overridesForLocale", {}).get("basicInformation") or {}
            per_locale.append(
                {
                    "locale": loc,
                    "name": override.get("name") or base_info.get("name"),
                    "description": override.get("description") or base_info.get(
                        "description"
                    ),
                }
            )
        results.append(
            {
                "id": pid,
                "name": per_locale[0]["name"],
                "overrides": per_locale,
            }
        )
    return results


@router.post("/update-basic-info")
async def update_basic_info(body: Dict[str, Any]):
    pid     = body["product_id"]
    locales = body["locales"]          # { 'es': {name, description}, ... }

    for loc, payload in locales.items():
        variables = {
            "input": {
                "productId": f"bc/store/product/{pid}",
                "localeContext": {
                    "channelId": f"bc/store/channel/{settings.BC_CHANNEL_ID}",
                    "locale": loc,
                },
                "data": {
                    "name": payload["name"],
                    "description": payload["description"],
                },
            },
            "channelId": f"bc/store/channel/{settings.BC_CHANNEL_ID}",
            "locale": loc,
        }
        _bc.graphql(get_update_mutation(), variables=variables, admin=True)

    return {"status": "ok", "updated": list(locales.keys())}
