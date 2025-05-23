from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any

from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.queries.gql_locale_queries import get_locales
from src.services.query_processors import process_gql_locales
from src.config import settings

from src.client.vertex_client import generate_multilingual_descriptions

router = APIRouter(tags=["generate"])
_bc = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
_srv = ProductLocalizationService(_bc)


class _Req(BaseModel):
    ids: List[int]
    base_language: str = "en"
    target_locales: List[str] | None = None
    channel_id: int | None = None


@router.post("/generate-overrides")
async def generate_overrides(body: _Req):
    chan = body.channel_id or settings.BC_CHANNEL_ID
    active = _active_locales(chan)
    targets = body.target_locales or [l for l in active if l != body.base_language]

    results: Dict[int, Any] = {}
    for pid in body.ids:
        base_data = _srv.get_localized_data(pid, chan, [body.base_language])
        base_name = base_data[body.base_language]["name"]
        base_desc = base_data[body.base_language]["description"]

        translations = generate_multilingual_descriptions(
            product_id=str(pid),
            name=base_name,
            features=base_desc,
            input_language=body.base_language,
            target_languages=targets,
        )
        if not translations:
            results[pid] = {"error": "vertex_fail"}
            continue

        local_payload = {l: {"name": t["product_name"], "description": t["description"]} for l, t in translations.items()}
        local_payload[body.base_language] = {"name": base_name, "description": base_desc}

        results[pid] = _srv.update_all_locales(pid, local_payload, chan)
    return {"results": results}


def _active_locales(channel_id):
    q, v = get_locales(channel_id)
    resp = _bc.graphql(q, variables=v, admin=True)
    return [c for c, meta in process_gql_locales(resp).items() if meta.get("status") == "ACTIVE"]