"""
SmartSafe V27 - External Webhook API Server
Exposes core functionality via a secure REST API using FastAPI.
"""

import logging
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from core.config import SETTINGS
from core.api.whatsapp_baileys import BaileysAPI

logger = logging.getLogger(__name__)

# --- API Setup ---
app = FastAPI(
    title="SmartSafe V27 Webhook API",
    description="API for triggering actions in SmartSafe from external systems.",
    version="1.0.0"
)

API_KEY = SETTINGS.get("WEBHOOK_API_KEY")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

async def get_api_key(key: str = Security(api_key_header)):
    """Dependency to validate the API key."""
    if not API_KEY:
        logger.warning("WEBHOOK_API_KEY is not set. API is unsecured!")
        return key # Allow if no key is set, but log a warning
    if key == API_KEY:
        return key
    else:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

# --- Pydantic Models ---
class SendMessageRequest(BaseModel):
    number: str
    message: str
    account: Optional[str] = None

# --- API Endpoints ---
@app.post("/api/v1/send_message", dependencies=[Depends(get_api_key)])
async def send_message(request: SendMessageRequest):
    """
    Sends a WhatsApp message via a specified account.
    """
    try:
        api = BaileysAPI()
        result = api.send_message(
            number=request.number,
            message=request.message,
            account=request.account
        )

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to send message"))

        return {"ok": True, "detail": "Message queued for sending.", "result": result}
    except Exception as e:
        logger.error(f"Webhook /send_message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))