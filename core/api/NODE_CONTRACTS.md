## Node API Contracts – SmartSafe V27

This document describes the **stable JSON contracts** between:

- **Node WhatsApp server** (`whatsapp-server/index.js`)
- **Python transport client** (`NodeService` in `node_service.py`)
- **High‑level WhatsApp facade** (`BaileysAPI` in `whatsapp_baileys.py`)

All consumers inside the Python codebase (engines, UI tabs, tests) **must only talk to
the Node server through `NodeService`/`BaileysAPI`**, never via raw `requests`.

Whenever the Node server responses change, you must update:

- This file (`NODE_CONTRACTS.md`)
- `core/api/node_service.py`
- `tests/test_node_contracts.py`

---

### 1. Normalized Python view

Every call made through `NodeService`/`BaileysAPI` returns a **normalized payload**
with (at minimum) the following top‑level keys:

- `ok: bool` – overall success flag
- `error: str | null` – human‑readable error message (present when `ok == false`)
- `code: str | null` – machine‑readable error code
- `status_code: int` – HTTP status code (0 for local/transport errors)
- `retryable: bool` – whether the error is considered transient

The Node server can add additional fields; `NodeService` preserves them and only
adds the normalization fields above when they are missing or inconsistent.

---

### 2. Endpoints

#### `/health` – Server health

- **Method**: `GET`
- **Auth**: no API key required

**Raw Node response (simplified)**:

```json
{
  "ok": true,
  "status": "online",
  "version": "1.x.y",
  "host": "127.0.0.1",
  "port": 4000,
  "timestamp": "2026-03-14T19:25:00.000Z"
}
```

**Python callers**:

- `NodeService.get_health()`
- `BaileysAPI.get_health()` (when called without `account`)

The Python view preserves all Node fields and adds:

- `status_code` – e.g. `200`
- `retryable` – always `false` for HTTP 200

---

#### `/status` – Account status

- **Method**: `GET`
- **Query**: optional `account=<string>` (when omitted, server selects a connected/default account)
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Success (200)**:

```json
{
  "ok": true,
  "account": "acc1",
  "status": "READY",
  "connected": true,
  "user": "123456789@s.whatsapp.net",
  "phone": "123456789",
  "number": "123456789",
  "device": {
    "number": "123456789",
    "model": "device-id-or-null",
    "platform": "platform-or-null",
    "login_time": null,
    "last_sync": null
  }
}
```

**Error (401)**:

```json
{
  "ok": false,
  "code": "UNAUTHORIZED",
  "error": "Unauthorized"
}
```

**Error (200) – not connected**:

```json
{
  "ok": false,
  "code": "ACCOUNT_NOT_CONNECTED",
  "error": "Account not connected",
  "account": "acc1",
  "connected": false,
  "status": "DISCONNECTED"
}
```

**Python callers**:

- `NodeService.get_status(account=None | str)`
- `BaileysAPI.get_health(account=...)`

On 4xx/5xx responses without `ok`, `NodeService` forces:

- `ok = false`
- `code = "HTTP_ERROR"` if Node did not provide `code`
- `error = "HTTP <status>"` if Node did not provide `error`

---

#### `/accounts` – Allowed accounts

- **Method**: `GET`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Success (200)**:

```json
{
  "ok": true,
  "accounts": [
    { "account": "acc1", "name": "acc1", "label": "acc1", "connected": true, "phone": "123456789" },
    { "account": "acc2", "name": "acc2", "label": "acc2", "connected": false, "phone": null }
  ],
  "current_account": "acc1"
}
```

**Python callers**:

- `NodeService.get_accounts()`
- `BaileysAPI.get_accounts()`

---

#### `/accounts-status` – Per‑account connection/state

- **Method**: `GET`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Success (200)**:

```json
{
  "ok": true,
  "status": {
    "acc1": { "connected": false, "ready": false }
  },
  "accounts": {
    "acc1": { "connected": false, "ready": false }
  }
}
```

**Python callers**:

- `NodeService.get_accounts_status()`
- `BaileysAPI.get_accounts_status()`

UI tabs such as `MultiEngineTab` use this data (via `BaileysAPI`) to show account
health and drive routing decisions.

---

#### `/stats` – Global server/transport stats

- **Method**: `GET`
- **Auth**: no API key required

**Success (200)**:

```json
{
  "ok": true,
  "connected": true,
  "total_sessions": 1,
  "sessions": {
    "acc1": { "connected": true, "user": "123456789@s.whatsapp.net" }
  },
  "stats": {
    "acc1": {
      "connected": true,
      "status": "READY",
      "messages_sent": 0,
      "profile_checks": 0,
      "errors": 0,
      "last_error": null,
      "last_sent_at": 1710000000,
      "last_profile_check_at": 1710000100
    }
  },
  "current_account": "acc1",
  "queue_length": 0,
  "server_time": "2026-03-14T19:25:00.000Z"
}
```

**Python callers**:

- `NodeService.get_stats()`
- `BaileysAPI.get_stats()`

UI tabs use:

- `stats[account].connected`
- `stats[account].messages_sent`
- `stats[account].errors`
- `queue_length` (or `queue`) when present

---

#### `/send` – Single message

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Request body (Python)**:

```json
{
  "number": "<E.164 number without +>",
  "message": "<text>",
  "account": "acc1",          // optional
  "media_url": "data:...;base64,..." // optional (data URL or remote URL)
}
```

`BaileysAPI.send_message`:

- Normalizes phone numbers with `normalize_phone`
- Encodes local media to `media_url` (data URL) when `media_path` is provided
- Delegates to `NodeService.send(...)`

**Success (200)**:

```json
{
  "ok": true,
  "account": "acc1",
  "number": "966500000000",
  "messageId": "BAILEYS_ID",
  "message_id": "BAILEYS_ID",
  "status": "sent",
  "timestamp": 1710000000
}
```

**Error (400)** – e.g. account not connected:

```json
{
  "ok": false,
  "code": "ACCOUNT_NOT_CONNECTED",
  "error": "Not connected",
  "account": "acc1",
  "number": "966500000000",
  "connected": false
}
```

`NodeService` preserves the Node body and adds `status_code`/`retryable` as needed.

---

#### `/send-bulk` – Bulk messages

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Request body (Python)**:

```json
{
  "messages": [
    { "number": "111", "message": "Hi 1" },
    { "number": "222", "message": "Hi 2" }
  ],
  "account": "acc1" // optional
}
```

**Success (200)**:

```json
{
  "ok": true,
  "account": "acc1",
  "sent": 0,
  "failed": 2,
  "results": [
    {
      "ok": false,
      "account": "acc1",
      "number": "111",
      "error": "Not connected"
    },
    {
      "ok": false,
      "account": "acc1",
      "number": "222",
      "error": "Not connected"
    }
  ]
}
```

**Python callers**:

- `NodeService.send_bulk(messages=[...], account=None | str)`
- `BaileysAPI.send_bulk(messages=[...])`

Each item in `results` includes `number`, `ok`, `account`, and either
`messageId`/`message_id` on success or `error` on failure.

---

#### `/profile-check` – Single profile lookup

- **Method**: `GET` or `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Request body (Python)**:

```json
{ "number": "<E.164 number without +>", "account": "acc1" }
```

**Success (200)**:

```json
{
  "ok": true,
  "account": "acc1",
  "number": "966500000000",
  "exists": true
}
```

**Error (400)** – in a fresh test environment:

```json
{
  "ok": false,
  "code": "ACCOUNT_NOT_CONNECTED",
  "error": "Not connected",
  "account": "acc1",
  "connected": false
}
```

`tests/test_node_contracts.py` accepts either `ACCOUNT_NOT_CONNECTED` or
`PROFILE_CHECK_FAILED` here, depending on server configuration.

**Python callers**:

- `NodeService.profile_check(number, account=None | str)`
- `BaileysAPI.check_profile` / `BaileysAPI.profile_check`

---

#### `/profile-check-bulk` – Bulk profile lookup

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`

**Request body (Python)**:

```json
{
  "numbers": ["111", "222"],
  "account": "acc1"
}
```

**Success (200)**:

```json
{
  "ok": true,
  "account": "acc1",
  "results": [
    { "account": "acc1", "number": "111", "exists": false },
    { "account": "acc1", "number": "222", "exists": false }
  ]
}
```

**Python callers**:

- `NodeService.profile_check_bulk(numbers=[...], account=None | str)`
- `BaileysAPI.check_profiles_bulk` / `BaileysAPI.profile_check_bulk`

Each element in `results` is shaped like a `/profile-check` response.

---

### 3. Account Management & Other Endpoints

This section documents endpoints for managing accounts and retrieving data.

#### `/qr` – Get QR code for login

- **Method**: `GET`
- **Path**: `/qr/:account?` (also supports `?account=...`)
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.get_qr(account=...)`

#### `/pairing-code` – Get pairing code

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Request body**: `{ "account": "acc1", "number": "123456789" }`
- **Python caller**: `BaileysAPI.get_pairing_code(account, number)`
- **Success Response**:

  ```json
  { "ok": true, "code": "ABCD-1234", "account": "acc1" }
  ```

#### `/connect/:account` – Connect an account

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.connect_account(account=...)`

#### `/reset/:account` – Reset/logout an account

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python callers**: `BaileysAPI.reset_account(account)`, `BaileysAPI.connect_account(..., force_reset=True)`

#### `/logout` – Logout an account

- **Method**: `GET` or `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Request body**: `{ "account": "acc1" }` (optional, POST)
- **Query**: `account=<string>` (optional, GET)
- **Python caller**: `BaileysAPI.logout(account=...)`

#### `/start-all` – Start all configured accounts

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.start_all_accounts()`

#### `/chat-list` – Get list of chats

- **Method**: `GET`
- **Query**: optional `account=<string>`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.get_chat_list(account=...)`

**Success (200)**:

```json
{
  "ok": true,
  "chats": [
    {
      "id": "123456789@s.whatsapp.net",
      "name": "Contact Name",
      "pushname": "Contact Name",
      "t": 1710000000,
      "count": 0,
      "unreadCount": 0,
      "isGroup": false
    }
  ]
}
```

#### `/all-contacts` – Get all contacts

- **Method**: `GET`
- **Query**: optional `account=<string>`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.get_all_contacts(account=...)`

**Success (200)**:

```json
{
  "ok": true,
  "contacts": [
    {
      "id": "123456789@s.whatsapp.net",
      "name": "Contact Name",
      "verifiedName": null,
      "isBusiness": false
    }
  ]
}
```

---

### 4. Message Tracking Endpoints

These endpoints are used for real-time message tracking, as described in `docs/TRACKING.md`.

#### `/track-message` – Register a message for tracking

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Request body**:

  ```json
  {
    "messageId": "<unique_id>",
    "phoneNumber": "<E.164 number>",
    "content": "<message text>",
    "account": "acc1"
  }
  ```

- **Python caller**: `BaileysAPI.track_message(...)`

#### `/message-status/:messageId` – Update message status

- **Method**: `POST`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Request body**: `{ "status": "<sent|delivered|read|failed>" }`
- **Python caller**: `BaileysAPI.update_message_status(...)`

#### `/incoming-messages` – Get recent incoming messages

- **Method**: `GET`
- **Query**: optional `since=<unix_timestamp>`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.get_incoming_messages(...)`
  - Note: the current Node implementation returns an empty list unless extended.

#### `/message/:messageId` – Get details for a tracked message

- **Method**: `GET`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.get_message_details(...)`

#### `/tracked-messages` – Get all tracked messages

- **Method**: `GET`
- **Auth**: `X-API-Key` required when `SMARTSAFE_REQUIRE_API_KEY=true`
- **Python caller**: `BaileysAPI.get_all_tracked_messages()`

---

### 5. Python–Node boundary rules

- All HTTP calls to the Node server **must** go through `NodeService` or
  a subclass such as `BaileysAPI`.
- Callers **must not** depend on raw HTTP status codes; instead, they should
  rely on:
  - `ok`
  - `code`
  - `error`
  - `retryable`
- When adding a new endpoint:
  - Extend `NodeService` with a dedicated helper method (and optionally
    `BaileysAPI` if it is WhatsApp‑specific).
  - Document the request/response shape here.
  - Extend `tests/test_node_contracts.py` with at least one contract test.
