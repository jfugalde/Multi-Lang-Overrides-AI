from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.api.products            import router as products_router
from src.api.overrides           import router as overrides_router
from src.api.generate            import router as generate_router
from src.api.product_with_overrides import router as pwo_router


from src.api import products, overrides, generate
from src.config import settings

app = FastAPI(title="BigTools Multilang AI", version="1.0.0")

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

# Include routers
app.include_router(products_router, prefix="/api")
app.include_router(overrides_router, prefix="/api")
app.include_router(generate_router,  prefix="/api")
app.include_router(pwo_router,       prefix="/api")
@app.get("/ui", response_class=HTMLResponse)
async def render_ui(request: Request):
    from src.operations.product_operations import ProductOperations
    from src.client.bc_client import BigCommerceClient

    client = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
    ops = ProductOperations(client)
    products = ops.get_bigcommerce_products(channel_id=settings.BC_CHANNEL_ID)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "products": products,
    })

@app.post("/generate", response_class=HTMLResponse)
async def handle_generation(
    request: Request,
    product_id: list[int] = Form(...),
    locale: list[str] = Form(...),
):
    # You can call your service here like:
    # localization_srv.update_all_locales(...)
    return RedirectResponse("/ui", status_code=302)

@app.get("/api/health")
async def health():
    return {"status": "ok"}

# Run
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
