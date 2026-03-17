"""
SmartSafe V27 - Flow Execution Engine
Executes visual chatbot flows created in the Flow Builder.
"""
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from core.api.whatsapp_baileys import BaileysAPI
from core.ai.ai_service import get_ai_service

logger = logging.getLogger(__name__)


class FlowEngine:
    """
    Interprets and executes conversation flows defined in a JSON format.
    """

    def __init__(self):
        self.api = BaileysAPI()
        self.ai_service = get_ai_service()
        self.active_sessions: Dict[str, Dict[str, Any]] = {}  # In-memory session store
        self._lock = threading.Lock()

    def load_flow(self, flow_definition: str) -> Dict[str, Any]:
        """Loads and validates a JSON flow definition."""
        try:
            flow = json.loads(flow_definition)
            # TODO: Add validation for flow structure (nodes, edges, start_node)
            logger.info(f"Successfully loaded flow with {len(flow.get('nodes', []))} nodes.")
            return flow
        except json.JSONDecodeError:
            logger.error("Failed to parse flow definition: invalid JSON.")
            return {}

    def handle_incoming_message(self, phone: str, message: str, flow: Dict[str, Any]):
        """
        Processes an incoming message against a loaded flow.
        This is the entry point for the chatbot logic.
        """
        with self._lock:
            session = self.active_sessions.get(phone, {
                "current_node": flow.get("start_node_id"),
                "variables": {}
            })

        current_node_id = session.get("current_node")
        if not current_node_id:
            logger.warning(f"No start node defined for flow. Cannot process message from {phone}.")
            return

        self._execute_node(phone, message, current_node_id, session, flow)

    def _execute_node(self, phone: str, message: str, node_id: str, session: Dict, flow: Dict):
        """Recursively executes nodes in the flow graph."""
        node = next((n for n in flow.get("nodes", []) if n["id"] == node_id), None)
        if not node:
            logger.error(f"Node ID {node_id} not found in flow definition.")
            return

        node_type = node.get("type")
        logger.info(f"Executing node {node_id} (type: {node_type}) for user {phone}.")

        if node_type == "sendMessage":
            text_to_send = node.get("data", {}).get("text", "")
            # TODO: Add variable substitution, e.g., text_to_send.format(**session["variables"])
            self.api.send_message(phone, text_to_send)
            # Find next node from edge
            # ...

        elif node_type == "condition":
            # Use AI or simple keyword matching to evaluate condition
            # ...
            pass

        elif node_type == "wait":
            delay = node.get("data", {}).get("seconds", 5)
            time.sleep(delay)
            # Find next node and execute
            # ...

        # Update session state
        with self._lock:
            self.active_sessions[phone] = session