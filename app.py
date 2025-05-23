from typing import List, Dict, Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.operations.product_operations import ProductOperations
from src.client.vertex_client import generate_multilingual_descriptions
from src.queries.gql_locale_queries import get_locales
from src.services.query_processors import process_gql_locales
from src import config

app = FastAPI(title="BigTools Multilang AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bc_client = BigCommerceClient(environment=config.BC_ENV or "production", debug=config.DEBUG_MODE)
localization_srv = ProductLocalizationService(bc_client)
product_ops = ProductOperations(bc_client)

class GenerateOverridesRequest(BaseModel):
    ids: List[int]
    channel_id: Optional[int] = None
    base_language: str = "en"
    target_locales: Optional[List[str]] = None

class GenerateOverridesResponse(BaseModel):
    results: Dict[int, Any]

def _active_locales(channel_id: int) -> List[str]:
    query, variables = get_locales(channel_id)
    locale_resp = bc_client.graphql(query, variables=variables, admin=True)
    locales_info = process_gql_locales(locale_resp)
    return [loc for loc, meta in locales_info.items() if meta.get("status") == "ACTIVE"]

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/products")
def list_products(channel_id: int = config.BC_CHANNEL_ID):
    """Return a simplified catalog suitable for the React table."""
    products = product_ops.get_bigcommerce_products(channel_id)
    # Flatten essential fields
    simplified = [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description", ""),
            "category": p.get("categories", [None])[0],
        }
        for p in products
    ]
    return simplified


@app.get("/api/overrides")
def list_overrides(channel_id: int = config.BC_CHANNEL_ID, ids: Optional[str] = None):
    """Return overrides for given product IDs (comma-sep) or the first 50 products."""
    if ids:
        prod_ids = [int(x) for x in ids.split(",") if x]
    else:
        prods = product_ops.get_bigcommerce_products(channel_id)[:50]
        prod_ids = [p["id"] for p in prods]

    overrides_rows = []
    for pid in prod_ids:
        # pulls all active locales for channel
        locales = _active_locales(channel_id)
        data = localization_srv.get_localized_data(pid, channel_id, locales)
        for locale, payload in data.items():
            overrides_rows.append(
                {
                    "id": pid,
                    "locale": locale,
                    "name": payload["name"],
                    "description": payload["description"],
                }
            )
    return overrides_rows


@app.post("/api/generate-overrides", response_model=GenerateOverridesResponse)
def generate_overrides(req: GenerateOverridesRequest):
    channel_id = req.channel_id or config.BC_CHANNEL_ID
    active_locales = _active_locales(channel_id)

    # Determine which locales need generation
    target_locales = (
        req.target_locales or [loc for loc in active_locales if loc != req.base_language]
    )

    results: Dict[int, Any] = {}
    for pid in req.ids:
        # Current EN data
        base_data = localization_srv.get_localized_data(pid, channel_id, [req.base_language])
        base_name = base_data[req.base_language]["name"]
        base_desc = base_data[req.base_language]["description"]

        translations, err = generate_multilingual_descriptions(
            product_id=str(pid),
            name=base_name,
            features=base_desc,
            input_language=req.base_language,
            target_languages=target_locales,
            return_error=True
        )

        if err:
            results[pid] = {"vertex_error": err}
            continue

        localized_payload = {
            lang: {
                "name": translations[lang]["product_name"],
                "description": translations[lang]["description"],
            }
            for lang in translations
        }
        # Also include base language (to overwrite or ensure parity)
        localized_payload[req.base_language] = {
            "name": base_name,
            "description": base_desc,
        }

        update_res = localization_srv.update_all_locales(pid, localized_payload, channel_id)
        results[pid] = update_res

    return {"results": results}
