# SmartSafe V27 - Message Tracking Overview

This document explains how message tracking works across the Node.js WhatsApp
server and the Python analytics / UI layers.

## Node.js WhatsApp Server (`whatsapp-server/whatsapp_server.js`)

- **In-memory tracker**: The Node server maintains an in-memory `messageTracker`
  object that stores:
  - Outgoing messages keyed by `messageId`
  - A rolling buffer of incoming messages (limited to the most recent 1000)
- **Key endpoints**:
  - `POST /track-message` – register an outgoing message by `messageId`,
    phone number, content, and account.
  - `POST /message-status/:messageId` – update delivery status for a tracked
    message (`pending`/`sent`/`delivered`/`read`/`failed`).
  - `GET /incoming-messages` – fetch recent incoming messages (optionally
    filtered by `since` timestamp).
  - `GET /message/:messageId` – fetch a single tracked message.
  - `GET /tracked-messages` – fetch all tracked messages currently in memory.
- **Enhanced `/send` endpoint**:
  - `POST /send` accepts `number`, `message`, and optional `messageId`.
  - When `messageId` is provided, the Node server:
    - Registers the message via `messageTracker.trackMessage`.
    - Sends the message via Baileys.
    - Updates status to `sent` (or `failed` on error).
- **Persistence behavior**:
  - Node-side tracking is **in-memory only** and is cleared when the Node
    process restarts.

## Python Tracking Layer (`core/tracking/`)

- Python code under `core/tracking/` is responsible for:
  - Persisting message and analytics data to local storage (e.g. SQLite).
  - Providing higher-level analytics and dashboards for the UI tabs.
  - Aggregating metrics over longer periods than the Node in-memory buffer.
- Typical responsibilities:
  - `message_tracking_service.py` – core message tracking and persistence.
  - `response_analytics.py` – response and performance analytics.
  - `response_monitor.py` – monitoring and alerting hooks.

## UI Tabs (`ui/tabs/`)

- **`message_tracking_tab.py`**:
  - Visualizes tracked messages and their delivery status.
  - Typically consumes data from the Python tracking layer, which may itself
    call Node endpoints for fresh status information.
- **`ml_analytics_tab.py`**:
  - Focuses on ML-powered analytics over tracked data.
  - Uses persisted tracking data rather than Node’s in-memory buffer alone.

## Source of Truth and Integration

- **Short-lived, real-time view**:
  - Node’s `messageTracker` is the immediate, in-memory source for the most
    recent messages and incoming events.
  - Suitable for real-time dashboards and quick status polls.

- **Durable, historical view**:
  - Python’s `core/tracking` layer is the source of truth for historical and
    analytical data (after data is pulled from Node and persisted).

- **Typical flow**:
  1. Python sends or schedules a message and generates a `messageId`.
  2. Python calls Node `/send` with the same `messageId`.
  3. Node tracks the message in `messageTracker` and updates status as events
     arrive from Baileys.
  4. Python periodically (or on demand) fetches tracking data from Node and
     persists it via `core/tracking`.
  5. UI tabs read from the Python tracking layer to render dashboards.

This separation allows Node to focus on real-time WhatsApp events, while Python
owns persistence and advanced analytics.

