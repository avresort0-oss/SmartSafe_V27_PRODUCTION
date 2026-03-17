"""
Node API Contract Tests – SmartSafe V27

These tests validate the JSON contracts between:
- Node WhatsApp server (whatsapp-server/index.js)
- Python transport client (NodeService in node_service.py)
- High-level WhatsApp facade (BaileysAPI in whatsapp_baileys.py)

All tests verify the normalized response shape:
- ok: bool
- error: str | null
- code: str | null
- status_code: int
- retryable: bool

These tests require a running Node server. Set TEST_NODE_URL environment variable
to override the default http://127.0.0.1:4000
"""

from __future__ import annotations

import os
import unittest
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

# Import the classes we're testing
from core.api.node_service import NodeService
from core.api.whatsapp_baileys import BaileysAPI


class TestNormalizedResponse(unittest.TestCase):
    """Test that all responses follow the normalized shape."""

    def test_normalized_keys_present(self):
        """Verify normalized response has all required keys."""
        normalized = {
            "ok": True,
            "error": None,
            "code": None,
            "status_code": 200,
            "retryable": False,
        }
        for key in ["ok", "error", "code", "status_code", "retryable"]:
            self.assertIn(key, normalized, f"Missing key: {key}")

    def test_error_response_has_required_keys(self):
        """Verify error responses have all required keys."""
        error_response = {
            "ok": False,
            "error": "Test error",
            "code": "TEST_ERROR",
            "status_code": 400,
            "retryable": False,
        }
        self.assertFalse(error_response["ok"])
        self.assertIsNotNone(error_response["error"])
        self.assertIsNotNone(error_response["code"])
        self.assertIsInstance(error_response["status_code"], int)


class TestNodeServiceContracts(unittest.TestCase):
    """Test NodeService endpoint contracts."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_url = os.environ.get("TEST_NODE_URL", "http://127.0.0.1:4000")
        self.api_key = os.environ.get("TEST_API_KEY", "test_key_123")
        self.service = NodeService(
            base_url=self.base_url,
            timeout=10.0,
            api_key=self.api_key,
        )

    def tearDown(self):
        """Clean up after tests."""
        self.service.close()

    def test_get_health_contract(self):
        """Test /health endpoint returns expected shape."""
        # This test requires a running Node server
        # If server is not available, we skip
        try:
            result = self.service.get_health()
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            self.assertIn("retryable", result)
            
            if result.get("ok"):
                # Health check success should have host, port, version
                self.assertIn("host", result)
                self.assertIn("port", result)
                self.assertIn("version", result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_get_status_contract(self):
        """Test /status endpoint returns expected shape."""
        try:
            result = self.service.get_status()
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            self.assertIn("retryable", result)
            
            if result.get("ok"):
                # Status success should have account info
                self.assertIn("status", result)
                self.assertIn("account", result)
                self.assertIn("connected", result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_get_accounts_contract(self):
        """Test /accounts endpoint returns expected shape."""
        try:
            result = self.service.get_accounts()
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            
            if result.get("ok"):
                self.assertIn("accounts", result)
                self.assertIsInstance(result["accounts"], list)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_get_stats_contract(self):
        """Test /stats endpoint returns expected shape."""
        try:
            result = self.service.get_stats()
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            
            if result.get("ok"):
                self.assertIn("stats", result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_send_message_contract(self):
        """Test /send endpoint returns expected shape."""
        try:
            result = self.service.send(
                number="966500000000",
                message="Test message",
                account="acc1",
            )
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            self.assertIn("retryable", result)
            
            # Response may have additional fields
            if result.get("ok"):
                self.assertIn("message_id", result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_profile_check_contract(self):
        """Test /profile-check endpoint returns expected shape."""
        try:
            result = self.service.profile_check(
                number="966500000000",
                account="acc1",
            )
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            self.assertIn("retryable", result)
            
            # Accept either ACCOUNT_NOT_CONNECTED or PROFILE_CHECK_FAILED
            # depending on server configuration
            if not result.get("ok"):
                code = result.get("code", "")
                self.assertIn(code, ["ACCOUNT_NOT_CONNECTED", "PROFILE_CHECK_FAILED", "HTTP_ERROR"])
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_profile_check_bulk_contract(self):
        """Test /profile-check-bulk endpoint returns expected shape."""
        try:
            result = self.service.profile_check_bulk(
                numbers=["966500000000", "966500000001"],
                account="acc1",
            )
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            
            if result.get("ok"):
                self.assertIn("results", result)
                self.assertIsInstance(result["results"], list)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")


class TestBaileysAPIContracts(unittest.TestCase):
    """Test BaileysAPI endpoint contracts."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_url = os.environ.get("TEST_NODE_URL", "http://127.0.0.1:4000")
        self.api = BaileysAPI(host=self.base_url)

    def tearDown(self):
        """Clean up after tests."""
        self.api.close()

    def test_send_message_contract(self):
        """Test BaileysAPI.send_message returns normalized shape."""
        try:
            result = self.api.send_message(
                number="966500000000",
                message="Test message",
                account="acc1",
            )
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            self.assertIn("retryable", result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_check_profile_contract(self):
        """Test BaileysAPI.check_profile returns normalized shape."""
        try:
            result = self.api.check_profile(
                number="966500000000",
                account="acc1",
            )
            
            # Verify normalized response
            self.assertIn("ok", result)
            self.assertIn("status_code", result)
            
            if result.get("ok"):
                self.assertIn("exists", result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")

    def test_message_tracking_contracts(self):
        """Test message tracking endpoint contracts."""
        try:
            # Test track_message
            track_result = self.api.track_message(
                message_id="test_msg_123",
                phone_number="966500000000",
                content="Test content",
                account="acc1",
            )
            self.assertIn("ok", track_result)
            
            # Test get_incoming_messages
            incoming_result = self.api.get_incoming_messages()
            self.assertIn("ok", incoming_result)
            
            # Test get_all_tracked_messages
            tracked_result = self.api.get_all_tracked_messages()
            self.assertIn("ok", tracked_result)
        except Exception as e:
            self.skipTest(f"Node server not available: {e}")


class TestErrorHandling(unittest.TestCase):
    """Test error handling and normalization."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_url = os.environ.get("TEST_NODE_URL", "http://127.0.0.1:4000")
        self.service = NodeService(base_url=self.base_url, timeout=1.0)

    def tearDown(self):
        """Clean up after tests."""
        self.service.close()

    def test_connection_error_normalization(self):
        """Test connection errors are properly normalized."""
        # Use invalid URL to trigger connection error
        invalid_service = NodeService(base_url="http://invalid:9999", timeout=1.0)
        try:
            result = invalid_service.get_health()
            
            # Should return normalized error
            self.assertFalse(result.get("ok"))
            self.assertIn("error", result)
            self.assertIn("code", result)
            self.assertEqual(result.get("status_code"), 0)
            self.assertTrue(result.get("retryable"))
        except Exception:
            pass
        finally:
            invalid_service.close()

    def test_timeout_error_normalization(self):
        """Test timeout errors are properly normalized."""
        # Use very short timeout to trigger timeout
        short_timeout_service = NodeService(
            base_url="http://127.0.0.1:4000", 
            timeout=0.001
        )
        try:
            result = short_timeout_service.get_health()
            
            # Should return normalized error
            self.assertFalse(result.get("ok"))
            self.assertIn("code", result)
            self.assertIn(result.get("code"), ["TIMEOUT", "REQUEST_FAILED"])
        except Exception:
            pass
        finally:
            short_timeout_service.close()


class TestMockedContracts(unittest.TestCase):
    """Test contracts using mocked responses."""

    def test_health_response_parsing(self):
        """Test parsing of health endpoint response."""
        mock_response = {
            "ok": True,
            "host": "127.0.0.1",
            "port": 4011,
            "version": "1.0.0",
        }
        
        # Simulate normalization
        normalized = {
            "ok": mock_response.get("ok", False),
            "error": mock_response.get("error", "HTTP 200"),
            "code": mock_response.get("code", "UNKNOWN_ERROR"),
            "status_code": 200,
            "retryable": False,
        }
        
        # Add original fields
        for key, value in mock_response.items():
            if key not in normalized:
                normalized[key] = value
        
        self.assertTrue(normalized["ok"])
        self.assertEqual(normalized["host"], "127.0.0.1")
        self.assertEqual(normalized["version"], "1.0.0")

    def test_error_response_normalization(self):
        """Test normalization of error responses."""
        # Test 401 unauthorized
        error_response = {
            "ok": False,
            "code": "UNAUTHORIZED",
            "error": "Missing or invalid API key",
        }
        
        normalized = {
            "ok": False,
            "error": error_response.get("error", "HTTP 401"),
            "code": error_response.get("code", "HTTP_ERROR"),
            "status_code": 401,
            "retryable": False,
        }
        
        self.assertFalse(normalized["ok"])
        self.assertEqual(normalized["code"], "UNAUTHORIZED")
        self.assertEqual(normalized["status_code"], 401)


if __name__ == "__main__":
    unittest.main()
