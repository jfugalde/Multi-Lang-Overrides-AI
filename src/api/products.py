# src/api/products.py
from fastapi import APIRouter, Query
from src.client.bc_client import BigCommerceClient
from src.operations import product_operations
from src.config import settings

router = APIRouter(tags=["products"])

_bc  = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
_ops = product_operations.ProductOperations(_bc)

@router.get("/products")
async def list_products(
    limit: int = Query(10, le=100),
    page:  int = Query(1,  ge=1),
    channel_id: int = settings.BC_CHANNEL_ID,
):
    offs = (page - 1) * limit
    products = _ops.get_bigcommerce_products(channel_id)[offs : offs + limit]
    return [
        {"id": p["id"], "name": p["name"], "description": p.get("description")}
        for p in products
    ]
