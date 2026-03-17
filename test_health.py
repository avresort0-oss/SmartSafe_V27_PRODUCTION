#!/usr/bin/env python
"""Quick test script to check health endpoint."""
import sys
sys.path.insert(0, '.')

from core.api.whatsapp_baileys import BaileysAPI

api = BaileysAPI()
result = api.get_health()
print("Health check result:")
print(f"  ok: {result.get('ok')}")
print(f"  error: {result.get('error')}")
print(f"  status_code: {result.get('status_code')}")
print(f"  Full response: {result}")

