from fastapi import Header, HTTPException

from app.mockbank.core.config import BANK_API_KEY


def require_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != BANK_API_KEY:
        raise HTTPException(status_code=401, detail="invalid api key")
