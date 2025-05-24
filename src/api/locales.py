from typing import List
from fastapi import APIRouter, Query

from src.client.bc_client import BigCommerceClient
from src.config import settings
from src.queries.gql_locale_queries import get_locales
from src.services.query_processors import process_gql_locales


_bc = BigCommerceClient(environment=settings.BC_ENV, debug=settings.DEBUG_MODE)
router = APIRouter(tags=["overrides"])

def active_locales(channel_id: int) -> List[str]:
    q, v = get_locales(channel_id)
    resp = _bc.graphql(q, variables=v, admin=True)
    return [loc for loc, meta in process_gql_locales(resp).items() if meta.get("status") == "ACTIVE"]

@router.get("/locales", response_model=List[str])
async def list_active_locales(
    channel_id: int = Query(settings.BC_CHANNEL_ID, ge=1)
):
    return active_locales(channel_id)