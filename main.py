"""
main.py – BigTools Multilang AI
FastAPI entry-point, endpoints ‘monolítico’ para PoC.
Si más adelante modularizas en routers, bastará con mover los bloques.
"""
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pydantic import BaseModel

from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.operations.product_operations import ProductOperations
from src.client.vertex_client import generate_multilingual_descriptions
from src.queries.gql_locale_queries import get_locales
from src.services.query_processors import process_gql_locales
from src import config

# ─────────────────────────── FastAPI APP ──────────────────────────
app = FastAPI(title="BigTools Multilang AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"],  allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# ─────────────────────────── Clients / Services ───────────────────
bc_client        = BigCommerceClient(environment=config.BC_ENV or "production",
                                     debug=config.DEBUG_MODE)
localization_srv = ProductLocalizationService(bc_client)
product_ops      = ProductOperations(bc_client)

# ─────────────────────────── Helpers ──────────────────────────────
def _active_locales(channel_id: int) -> List[str]:
    """Locales en estado ACTIVE para el canal dado."""
    query, variables = get_locales(channel_id)
    resp   = bc_client.graphql(query, variables=variables, admin=True)
    return [
        loc for loc, meta in process_gql_locales(resp).items()
        if meta.get("status") == "ACTIVE"
    ]

# ─────────────────────────── Schemas ──────────────────────────────
class GenerateOverridesRequest(BaseModel):
    ids: List[int]
    channel_id: Optional[int] = None
    base_language: str = "en"
    target_locales: Optional[List[str]] = None

class GenerateOverridesResponse(BaseModel):
    results: Dict[int, Any]

# ─────────────────────────── Basic & UI ───────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "env": config.BC_ENV, "channel": config.BC_CHANNEL_ID}

@app.get("/ui", response_class=HTMLResponse)
def render_ui(request: Request):
    """Dev-only: entrega index.html; el JS pega a la REST API."""
    return templates.TemplateResponse("index.html", {"request": request})

# ─────────────────────────── Catalog / Products ───────────────────
@app.get("/api/products")
def list_products(channel_id: int = config.BC_CHANNEL_ID,
                  limit: int = Query(250, le=250, ge=1),
                  page : int = Query(1,   ge=1)):
    """Catálogo simplificado (paginar desde frontend con ?page=)."""
    offs = (page - 1) * limit
    products = product_ops.get_bigcommerce_products(channel_id)[offs : offs + limit]
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p.get("description", ""),
            "price": p.get("price"),
            "category": (p.get("categories") or [None])[0],
        }
        for p in products
    ]

# ─────────────────────────── Locales ──────────────────────────────
@app.get("/api/locales", response_model=List[str])
def list_locales(channel_id: int = config.BC_CHANNEL_ID):
    """Locales activos para poblar los checkboxes del front-end."""
    return _active_locales(channel_id)

# ─────────────────────────── GET overrides (matrix) ───────────────
@app.get("/api/overrides")
def list_overrides(channel_id: int = config.BC_CHANNEL_ID,
                   ids: Optional[str] = None):
    """
    Devuelve todas las traducciones (name+description) por producto/locale.
    Si no se pasan IDs → usa los primeros 50 productos para demo.
    """
    prod_ids = ([int(x) for x in ids.split(',') if x] if ids
                else [p["id"] for p in product_ops.get_bigcommerce_products(channel_id)[:50]])

    rows: List[Dict[str, Any]] = []
    locales = _active_locales(channel_id)
    for pid in prod_ids:
        data = localization_srv.get_localized_data(pid, channel_id, locales)
        for loc, payload in data.items():
            rows.append({"id": pid, "locale": loc,
                         "name": payload["name"],
                         "description": payload["description"]})
    return rows

# ─────────────────────────── GET products-with-overrides ──────────
@app.get("/api/products-with-overrides")
def products_with_overrides(ids: Optional[str] = Query(None,
                                                      description="Comma-sep product IDs"),
                            page: int = Query(1, ge=1),
                            limit: int = Query(10, le=100),
                            channel_id: int = config.BC_CHANNEL_ID):
    """Estructura que usa la SPA para ‘View Overrides’ y ‘Edit’."""
    if ids:
        try:
            product_ids = [int(x) for x in ids.split(",") if x]
        except ValueError:
            raise HTTPException(status_code=400, detail="'ids' must be integers")
    else:
        resp = bc_client.rest("/catalog/products", params={"limit": limit, "page": page})
        product_ids = [p["id"] for p in resp.get("data", [])]

    locales = _active_locales(channel_id)
    items   = []
    for pid in product_ids:
        per_locale = localization_srv.get_localized_data(pid, channel_id, locales)
        if not per_locale:
            continue
        # Usamos la primera locale para ‘name’ base
        default_name = next(iter(per_locale.values()))["name"]
        items.append({
            "id": pid,
            "name": default_name,
            "overrides": [
                {"locale": loc,
                 "name":  data["name"],
                 "description": data["description"]}
                for loc, data in per_locale.items()
            ],
        })
    return items

# ─────────────────────────── POST generate-overrides ──────────────
@app.post("/api/generate-overrides", response_model=GenerateOverridesResponse)
def generate_overrides(req: GenerateOverridesRequest):
    chan           = req.channel_id or config.BC_CHANNEL_ID
    active_locales = _active_locales(chan)
    targets        = (req.target_locales or
                      [l for l in active_locales if l != req.base_language])

    results: Dict[int, Any] = {}
    for pid in req.ids:
        base = localization_srv.get_localized_data(pid, chan, [req.base_language])
        b_name = base[req.base_language]["name"]
        b_desc = base[req.base_language]["description"]

        translations, err = generate_multilingual_descriptions(
            product_id=str(pid), name=b_name, features=b_desc,
            input_language=req.base_language, target_languages=targets,
            return_error=True)

        if err:
            results[pid] = {"vertex_error": err}
            continue

        # Build payload incl. base language
        payload = {req.base_language: {"name": b_name, "description": b_desc}}
        for lang, t in (translations or {}).items():
            payload[lang] = {"name": t["product_name"], "description": t["description"]}

        results[pid] = localization_srv.update_all_locales(pid, payload, chan)
    return {"results": results}

# ─────────────────────────── POST update-basic-info ───────────────
@app.post("/api/update-basic-info")
def update_basic_info(body: Dict[str, Any]):
    """
    body = { \"product_id\": 123, \"locales\": { \"es\": {name, description}, … } }
    Utilizado por el modo ‘Edit Storefront’ de la SPA.
    """
    pid     = body["product_id"]
    locales = body["locales"]
    chan_id = config.BC_CHANNEL_ID

    for loc, payload in locales.items():
        localization_srv.update_localized_product(
            product_id=pid,
            name       =payload.get("name", ""),
            description=payload.get("description", ""),
            locale     =loc,
            channel_id =chan_id,
        )
    return {"status": "ok", "updated": list(locales.keys())}

# ─────────────────────────── Dev runner ───────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)