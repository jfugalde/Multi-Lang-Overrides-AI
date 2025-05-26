from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.client.bc_client import BigCommerceClient
from src.services.product_multilang_service import ProductLocalizationService
from src.operations.product_operations import ProductOperations
from src.queries.gql_locale_queries import get_locales
from src.services.query_processors import process_gql_locales
from src.api.generate import router as generate_router
from src import config

# ─────────────────────────── FastAPI APP ──────────────────────────
app = FastAPI(title="BigTools Multilang AI", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"],  allow_headers=["*"],
)
app.include_router(generate_router)

templates = Jinja2Templates(directory="templates")

# ─────────────────────────── Clients / Services ───────────────────
bc_client        = BigCommerceClient(environment=config.BC_ENV or "production",
                                     debug=config.DEBUG_MODE)
localization_srv = ProductLocalizationService(bc_client)
product_ops      = ProductOperations(bc_client)

# ─────────────────────────── Helpers ──────────────────────────────
def _active_locales(channel_id: int) -> List[str]:
    q, v  = get_locales(channel_id)
    resp  = bc_client.graphql(q, variables=v, admin=True)
    return [code for code, meta in process_gql_locales(resp).items()
            if meta.get("status") == "ACTIVE"]

# ─────────────────────────── Basic & UI ───────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "env": config.BC_ENV, "channel": config.BC_CHANNEL_ID}

@app.get("/ui", response_class=HTMLResponse)
def render_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ─────────────────────────── Catalog / Products ───────────────────
@app.get("/api/products")
def list_products(channel_id: int = config.BC_CHANNEL_ID,
                  limit: int = Query(250, le=250, ge=1),
                  page:  int = Query(1,   ge=1)):
    offs = (page - 1) * limit
    prod = product_ops.get_bigcommerce_products(channel_id)[offs:offs+limit]
    return [{"id":p["id"],"name":p["name"],
             "description":p.get("description",""),
             "price":p.get("price"),
             "category":(p.get("categories")or[None])[0]} for p in prod]

# ─────────────────────────── Locales ──────────────────────────────
@app.get("/api/locales", response_model=List[str])
def list_locales(channel_id: int = config.BC_CHANNEL_ID):
    return _active_locales(channel_id)

# ─────────────────────────── GET overrides (matrix) ───────────────
@app.get("/api/overrides")
def list_overrides(channel_id: int = config.BC_CHANNEL_ID, ids: Optional[str] = None):
    prod_ids = ([int(x) for x in ids.split(',') if x] if ids
                else [p["id"] for p in product_ops.get_bigcommerce_products(channel_id)[:50]])

    locales = _active_locales(channel_id)
    rows: List[Dict[str, Any]] = []
    for pid in prod_ids:
        data = localization_srv.get_localized_data(pid, channel_id, locales)
        for loc,payload in data.items():
            rows.append({"id":pid,"locale":loc,"name":payload["name"],"description":payload["description"]})
    return rows

# ─────────────────────────── GET products-with-overrides ──────────
@app.get("/api/products-with-overrides")
def products_with_overrides(ids: Optional[str]=Query(None), page:int=1, limit:int=10,
                            channel_id:int=config.BC_CHANNEL_ID):
    if ids:
        try:     product_ids=[int(x) for x in ids.split(',') if x]
        except:  raise HTTPException(400,"'ids' must be integers")
    else:
        resp=bc_client.rest("/catalog/products",params={"limit":limit,"page":page})
        product_ids=[p["id"] for p in resp.get("data",[])]

    locales=_active_locales(channel_id)
    items=[]
    for pid in product_ids:
        per=localization_srv.get_localized_data(pid,channel_id,locales)
        if not per: continue
        items.append({
            "id":pid,
            "name":next(iter(per.values()))["name"],
            "overrides":[{"locale":loc,"name":d["name"],"description":d["description"]} for loc,d in per.items()]
        })
    return items

# ─────────────────────────── POST update-basic-info ───────────────
@app.post("/api/update-basic-info")
def update_basic_info(body: Dict[str, Any]):
    pid     = body["product_id"]
    locales = body["locales"]
    chan_id = config.BC_CHANNEL_ID
    for loc,payload in locales.items():
        localization_srv.update_localized_product(
            product_id=pid, channel_id=chan_id, locale=loc,
            name=payload.get("name",""), description=payload.get("description",""))
    return {"status":"ok","updated":list(locales.keys())}

# ─────────────────────────── Dev runner ───────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app",host="127.0.0.1",port=8000,reload=True)