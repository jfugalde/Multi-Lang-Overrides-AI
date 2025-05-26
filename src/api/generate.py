from typing import List, Dict, Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from src.api.locales import active_locales
from src.config import settings
from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.client.vertex_client import generate_multilingual_descriptions

router = APIRouter(prefix="/api", tags=["generate"])

_bc  = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
_srv = ProductLocalizationService(_bc)

class GenerateReq(BaseModel):
    ids:            List[int]
    base_language:  str = "en"
    target_locales: Optional[List[str]] = None
    channel_id:     Optional[int]  = None

@router.post("/generate-overrides")
async def generate_overrides(body: GenerateReq):
    channel_id      = body.channel_id or settings.BC_CHANNEL_ID
    active_full     = active_locales(channel_id)

    if body.target_locales:
        vertex_targets = [l for l in body.target_locales if l != body.base_language]
    else:
        vertex_targets = [l for l in active_full if l != body.base_language]

    results: Dict[int, Any] = {}

    for pid in body.ids:
        base = _srv.get_localized_data(pid, channel_id, [body.base_language])
        base_name = base[body.base_language]["name"]
        base_desc = base[body.base_language]["description"]

        translations, err = generate_multilingual_descriptions(
            product_id=str(pid),
            name           = base_name,
            features       = base_desc,
            input_language = body.base_language,
            target_languages = vertex_targets,
            return_error   = True,
        )

        if err or not translations:
            results[pid] = {"vertex_error": err or "empty_response"}
            continue

        payload = {
            body.base_language: {"name": base_name, "description": base_desc}
        }
        for full_code, t in translations.items():
            payload[full_code] = {
                "name":        t["product_name"],
                "description": t["description"],
            }
        results[pid] = _srv.update_all_locales(pid, payload, channel_id)

    return {"results": results}