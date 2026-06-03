from fastapi import APIRouter

from ..store import store

router = APIRouter(tags=["market"])


@router.get("/market-signals")
def list_market_signals():
    store.refresh_market_via_service()
    return store.market_signals


@router.get("/market-forecast")
def list_market_forecast():
    return store.market_forecast
