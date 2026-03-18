"""
SmartSafe V27 - Flow Execution Engine
Executes visual chatbot flows created in the Flow Builder.
"""

import asyncio
import aiohttp
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.api.whatsapp_baileys import BaileysAPI
from core.ai.ai_service import get_ai_service
from core.automation.translation import get_translation_service
from core.automation.image_recognition import get_image_service
from core.automation.voice_bot import get_voice_service

logger = logging.getLogger(__name__)


class FlowEngine:
    """
    Interprets and executes conversation flows defined in a JSON format.
    """

    def __init__(self):
        self.api = BaileysAPI()
        self.ai_service = get_ai_service()
        self.sessions_file = Path("sessions.json")
        self.active_sessions: Dict[str, Dict[str, Any]] = (
            self._load_sessions_from_disk()
        )
        self._lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

    def _load_sessions_from_disk(self) -> Dict[str, Dict[str, Any]]:
        """Loads active sessions from a JSON file on startup."""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, "r", encoding="utf-8") as f:
                    logger.info("Loading persistent sessions from disk.")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Could not load sessions file: {e}. Starting fresh.")
        return {}

    def _save_sessions_to_disk(self):
        """Saves the current active_sessions dictionary to a JSON file."""
        with self._lock, open(self.sessions_file, "w", encoding="utf-8") as f:
            json.dump(self.active_sessions, f, indent=2)

    def load_flow(self, flow_definition: str) -> Dict[str, Any]:
        """Loads and validates a JSON flow definition."""
        try:
            flow = json.loads(flow_definition)
            # TODO: Add validation for flow structure (nodes, edges, start_node)
            logger.info(
                f"Successfully loaded flow with {len(flow.get('nodes', []))} nodes."
            )
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
            session = self.active_sessions.get(phone)

        # If a session exists and is waiting for input, process it.
        if session and session.get("waiting_for_input"):
            variable_to_store = session["waiting_for_input"]
            session["variables"][variable_to_store] = message
            session["waiting_for_input"] = None

            next_node_id = session.get("current_node")
            if not next_node_id:
                logger.warning(f"Flow ended for {phone} after receiving input.")
                if phone in self.active_sessions:
                    del self.active_sessions[phone]
                self._save_sessions_to_disk()
                return

            # Resume flow execution from the next node
            self.schedule_execution(
                self._execute_node, args=[phone, message, next_node_id, session, flow]
            )

        # Otherwise, treat it as a trigger to start a new flow.
        else:
            start_node_id = flow.get("start_node_id")
            if not start_node_id:
                logger.warning(
                    f"No start node defined for flow. Cannot process message from {phone}."
                )
                return

            new_session = {
                "current_node": start_node_id,
                "variables": {},
                "waiting_for_input": None,
            }
            # Store the new session immediately
            with self._lock:
                self.active_sessions[phone] = new_session
            self._save_sessions_to_disk()

            self.schedule_execution(
                self._execute_node,
                args=[phone, message, start_node_id, new_session, flow],
            )

    async def _execute_node(
        self, phone: str, message: str, node_id: str, session: Dict, flow: Dict
    ):
        """Executes a node and schedules the next one if applicable."""
        node = next((n for n in flow.get("nodes", []) if n["id"] == node_id), None)
        if not node:
            logger.error(f"Node ID {node_id} not found in flow definition.")
            return

        node_type = node.get("type")
        logger.info(f"Executing node {node_id} (type: {node_type}) for user {phone}.")

        next_node_id = None

        if node_type == "sendMessage":
            text_to_send = node.get("data", {}).get("text", "")
            # Simple variable substitution
            variables = session.get("variables", {})
            try:
                text_to_send = text_to_send.format(**variables)
            except KeyError as e:
                logger.warning(
                    f"Variable {e} not found for user {phone}. Sending raw text."
                )
            except Exception:
                pass  # Ignore other formatting errors

            self.api.send_message(phone, text_to_send)
            next_node_id = node.get("next_node_id")

        elif node_type == "condition":
            data = node.get("data", {})
            logic = data.get("logic", "AND").upper()
            rules = data.get("rules", [])

            # Evaluate all rules
            rule_results = []
            for rule in rules:
                variable_name = rule.get("variable")
                operator = rule.get("operator", "equals")
                rule_value = rule.get("value")

                # Get actual value from session variables or message
                actual_value = session.get("variables", {}).get(variable_name)
                if variable_name == "last_message":
                    actual_value = message

                # Evaluate rule using the helper method
                rule_result = self._evaluate_rule(actual_value, operator, rule_value)
                rule_results.append(rule_result)

            # Apply logic (AND/OR)
            if logic == "AND":
                condition_result = all(rule_results)
            elif logic == "OR":
                condition_result = any(rule_results)
            else:
                # Default to AND for unknown logic
                condition_result = all(rule_results)

            next_node_id = (
                node.get("true_node_id")
                if condition_result
                else node.get("false_node_id")
            )

        elif node_type == "getUserInput":
            variable_name = node.get("data", {}).get("variable", "last_reply")
            session["waiting_for_input"] = variable_name
            session["current_node"] = node.get(
                "next_node_id"
            )  # Set the next node to execute after input is received

            # Update session and pause execution
            with self._lock:
                self.active_sessions[phone] = session
            self._save_sessions_to_disk()
            logger.info(
                f"Flow for {phone} is now waiting for user input, to be stored in '{variable_name}'."
            )
            return  # Stop execution, wait for next message

        elif node_type == "wait":
            delay = node.get("data", {}).get("seconds", 5)
            next_node_id_for_timer = node.get("next_node_id")
            if next_node_id_for_timer:
                logger.info(
                    f"Waiting for {delay}s before executing {next_node_id_for_timer} for {phone}"
                )

                # Schedule after delay
                async def delayed_execute():
                    await asyncio.sleep(delay)
                    await self._execute_node(
                        phone, message, next_node_id_for_timer, session, flow
                    )

                self._loop.create_task(delayed_execute())
            return  # Stop execution, task will handle the next step

        elif node_type == "apiCall":
            data = node.get("data", {})
            url = data.get("url", "")
            method = data.get("method", "GET").upper()
            headers = data.get("headers", {})
            body = data.get("body", {})
            response_variable = data.get("response_variable", "api_response")

            variables = session.get("variables", {})
            try:
                url = url.format(**variables)
            except KeyError as e:
                logger.warning(
                    f"Variable {e} not found for API call URL. Using raw URL."
                )

            try:
                async with aiohttp.ClientSession() as session_http:
                    async with session_http.request(
                        method,
                        url,
                        headers=headers,
                        json=body,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        response.raise_for_status()
                        result = await response.json()
                        session["variables"][response_variable] = result
                        next_node_id = node.get("next_node_id")
                        logger.info(f"API call to {url} successful for user {phone}.")
            except aiohttp.ClientError as e:
                logger.error(f"API call failed for user {phone}: {e}")
                session["variables"][response_variable] = {"error": str(e)}
                next_node_id = node.get("error_node_id")

        elif node_type == "sendMedia":
            data = node.get("data", {})
            media_url = data.get("url", "").format(**session.get("variables", {}))
            caption = data.get("caption", "").format(**session.get("variables", {}))
            self.api.send_message(phone, caption, media_url=media_url)
            next_node_id = node.get("next_node_id")

        elif node_type == "setVariable":
            data = node.get("data", {})
            var_name = data.get("variable")
            value = data.get("value")

            if var_name:
                # Allow referencing other variables in the value (e.g. "{first_name}_status")
                if isinstance(value, str):
                    try:
                        value = value.format(**session.get("variables", {}))
                    except Exception:
                        pass
                session["variables"][var_name] = value
                logger.info(f"Set variable '{var_name}' to '{value}' for user {phone}.")
            next_node_id = node.get("next_node_id")

        elif node_type == "aiCondition":
            data = node.get("data", {})
            prompt_template = data.get(
                "prompt",
                "Does this message mean 'yes'? Answer with only 'true' or 'false'.",
            )
            input_variable_name = data.get("input_variable", "last_message")

            # Get the input text from session variables or the last message
            variables = session.get("variables", {})
            input_text = (
                message
                if input_variable_name == "last_message"
                else variables.get(input_variable_name, "")
            )

            # Construct the full prompt for the AI
            full_prompt = f"Context: You are an AI assistant in a chatbot flow. Evaluate the following user input and answer the question with only the word 'true' or 'false'.\n\nUser Input: \"{input_text}\"\n\nQuestion: {prompt_template}"

            try:
                # Call the AI service
                ai_response = self.ai_service._call_ai(full_prompt)
                logger.info(
                    f"AI condition check for user {phone}. Prompt: '{prompt_template}'. AI response: '{ai_response}'"
                )

                next_node_id = (
                    node.get("true_node_id")
                    if "true" in ai_response.lower()
                    else node.get("false_node_id")
                )

            except Exception as e:
                logger.error(f"AI condition node failed for user {phone}: {e}")
                next_node_id = node.get(
                    "false_node_id"
                )  # Default to the false path on AI error

        elif node_type == "translate":
            data = node.get("data", {})
            text_variable = data.get("text_variable", "last_message")
            target_lang = data.get("target_language", "en")
            output_variable = data.get("output_variable", "translated_text")

            variables = session.get("variables", {})
            text_to_translate = variables.get(text_variable, message)

            translation_service = get_translation_service()
            if translation_service:
                translated = translation_service.translate_text(
                    text_to_translate, target_lang
                )
                session["variables"][output_variable] = translated
                logger.info(f"Translated text to {target_lang}: {translated}")
            else:
                session["variables"][output_variable] = text_to_translate
                logger.warning("Translation service not available")

            next_node_id = node.get("next_node_id")

        elif node_type == "imageAnalysis":
            data = node.get("data", {})
            image_url = data.get("image_url", "")
            output_variable = data.get("output_variable", "image_analysis")

            # Download and analyze image
            try:
                async with aiohttp.ClientSession() as session_http:
                    async with session_http.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
                            image_service = get_image_service()
                            if image_service:
                                analysis = image_service.analyze_image(image_data)
                                session["variables"][output_variable] = analysis
                                logger.info(f"Image analysis: {analysis}")
                            else:
                                session["variables"][output_variable] = {
                                    "error": "Image service not available"
                                }
                        else:
                            session["variables"][output_variable] = {
                                "error": f"Failed to download image: {resp.status}"
                            }
            except Exception as e:
                session["variables"][output_variable] = {"error": str(e)}
                logger.error(f"Image analysis failed: {e}")

            next_node_id = node.get("next_node_id")

        elif node_type == "voiceMessage":
            data = node.get("data", {})
            audio_url = data.get("audio_url", "")
            language = data.get("language", "en-US")
            output_variable = data.get("output_variable", "transcribed_text")

            voice_service = get_voice_service()
            if voice_service:
                # This is simplified - would need to download audio first
                transcribed = voice_service.process_voice_message(audio_url, language)
                session["variables"][output_variable] = transcribed
                logger.info(f"Voice transcribed: {transcribed}")
            else:
                session["variables"][output_variable] = "Voice service not available"

            next_node_id = node.get("next_node_id")

        # --- End of node type handling ---

        if next_node_id:
            # Schedule next node execution immediately
            # This avoids deep recursion for long chains of non-blocking nodes
            self.schedule_execution(
                self._execute_node, args=[phone, message, next_node_id, session, flow]
            )
        else:
            # Flow ended
            with self._lock:
                if phone in self.active_sessions:
                    del self.active_sessions[phone]
            self._save_sessions_to_disk()
            logger.info(f"Flow for {phone} has ended.")

    def _evaluate_rule(
        self, actual_value: Any, operator: str, value_to_compare: Any
    ) -> bool:
        """Evaluates a single rule within a condition node."""
        if actual_value is None:
            return operator == "not_exists"

        if operator == "exists":
            return True

        # Attempt to cast for numeric comparisons
        try:
            num_actual = float(actual_value)
            num_compare = float(value_to_compare)
            if operator == "greater_than":
                return num_actual > num_compare
            if operator == "less_than":
                return num_actual < num_compare
            if operator == "equals":
                return num_actual == num_compare
            if operator == "not_equals":
                return num_actual != num_compare
        except (ValueError, TypeError):
            # Not numeric, proceed with string comparison
            pass

        # String comparisons
        str_actual = str(actual_value).lower()
        str_compare = str(value_to_compare).lower()

        if operator == "equals":
            return str_actual == str_compare
        if operator == "not_equals":
            return str_actual != str_compare
        if operator == "contains":
            return str_compare in str_actual
        if operator == "starts_with":
            return str_actual.startswith(str_compare)
        if operator == "ends_with":
            return str_actual.endswith(str_compare)

        return False

    def schedule_execution(self, target, args):
        """Schedules a function to run asynchronously."""
        self._loop.create_task(self._async_execute(target, args))

    async def _async_execute(self, target, args):
        """Run the target function in the event loop."""
        try:
            await target(*args)
        except Exception as e:
            logger.error(f"Error in async execution: {e}")
