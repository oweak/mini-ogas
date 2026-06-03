import os
import secrets
import uuid
from random import uniform

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel


def _session_token() -> str:
    token = os.environ.get("OGAS_SESSION_TOKEN")
    if not token:
        token = str(uuid.uuid4())
        os.environ["OGAS_SESSION_TOKEN"] = token
    return token


app = FastAPI(title="Mini-OGAS Market Simulator", version="0.1.0")

_token_scheme = APIKeyHeader(name="X-OGAS-Token", auto_error=False)
_expected_token = os.getenv("API_ACCESS_TOKEN", "mini-ogas-dev-token")


def _verify_token(token: str | None = Depends(_token_scheme)) -> None:
    if not token or not secrets.compare_digest(token, _expected_token):
        raise HTTPException(status_code=401, detail="missing or invalid X-OGAS-Token")


class MarketSignal(BaseModel):
    product_code: str
    current_price: float
    competitor_price: float
    demand_index: float
    season_factor: float
    inventory_pressure: float


PRODUCTS = {
    "P1": 120.0,
    "P2": 180.0,
    "P3": 260.0,
    "P4": 310.0,
    "P5": 420.0,
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "market-simulator", "session_token": _session_token()}


@app.get("/signals", response_model=list[MarketSignal])
def signals(_: None = Depends(_verify_token)) -> list[MarketSignal]:
    result: list[MarketSignal] = []
    for product_code, base_price in PRODUCTS.items():
        season = uniform(0.85, 1.25)
        demand = uniform(50, 130) * season
        result.append(
            MarketSignal(
                product_code=product_code,
                current_price=round(base_price * uniform(0.95, 1.08), 2),
                competitor_price=round(base_price * uniform(0.9, 1.12), 2),
                demand_index=round(demand, 2),
                season_factor=round(season, 2),
                inventory_pressure=round(uniform(0, 100), 2),
            )
        )
    return result

