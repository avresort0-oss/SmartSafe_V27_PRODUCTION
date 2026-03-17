# WhiskeySockets/Baileys Integration for SmartSafe V27

This integration provides a robust WhatsApp API implementation using WhiskeySockets/Baileys for SmartSafe V27 Production Ready.

## Components

- **WhatsApp Server**: Node.js server using WhiskeySockets/Baileys
- **Python API**: High-level API wrapper for the WhatsApp server
- **Testing Framework**: Comprehensive testing tools for all aspects of the integration

## Features

- **Multi-Device Support**: Works with WhatsApp's multi-device protocol
- **Multiple Accounts**: Support for up to 10 WhatsApp accounts simultaneously
- **Enhanced Media Handling**: Support for images, videos, audio, and documents
- **Profile Information**: Extended profile checks with profile pictures and status text
- **Message Tracking**: Robust tracking of message delivery status (sent, delivered, read, played)
- **Improved Reconnection**: Intelligent backoff strategy with automatic reconnection
- **In-Memory Store**: Better performance with optimized data storage
- **Error Resilience**: Improved error handling and recovery mechanisms

## Setup Instructions

### 1. Install Dependencies

```bash
# Navigate to the WhatsApp server directory
cd whatsapp-server

# Install Node.js dependencies
npm install @whiskeysockets/baileys@latest @hapi/boom pino qrcode express cors
```

### 2. Start the WhatsApp Server

#### On Linux/Mac

```bash
# Make the script executable
chmod +x start_whatsapp_server.sh

# Run the script
./start_whatsapp_server.sh
```

#### On Windows

```batch
start_whatsapp_server.bat
```

### 3. Connect WhatsApp Account

```python
from core.api.whatsapp_baileys import BaileysAPI

# Initialize API
api = BaileysAPI(host="http://localhost:4000")

# Connect account
api.connect_account("acc1")

# Get QR code for scanning
qr_result = api.get_qr("acc1")
if qr_result["ok"] and qr_result["qr"]:
    print("Scan this QR code with your WhatsApp app:")
    print(qr_result["qr"])
```

## Testing

### Run Simulation Tests

These tests don't require a running server:

```bash
python simulate_api_tests.py
```

### Run Live Tests

These tests require a running server:

```bash
# Replace with your actual test number
python test_whatsapp_api.py critical
```

Available test types:

- `critical`: Basic connectivity, messaging, and account tests
- `media`: Media handling tests (images, documents, remote media)
- `multi-account`: Multi-account support tests
- `all`: All tests

### Automated Testing

The automation script handles server startup, testing, and cleanup:

```bash
# Run critical tests with default test number
python automate_whatsapp.py

# Run specific test type with custom test number
python automate_whatsapp.py media 1234567890
```

## API Usage Examples

### Send a Text Message

```python
result = api.send_message(
    number="1234567890",
    message="Hello from WhatsApp API!",
    message_id="msg_001"
)
```

### Send a Message with Media

```python
# Send an image
result = api.send_message(
    number="1234567890",
    message="Check out this image!",
    media_path="/path/to/image.jpg",
    message_id="msg_002"
)

# Send a document
result = api.send_message(
    number="1234567890",
    message="Here's the document you requested",
    media_path="/path/to/document.pdf",
    message_id="msg_003"
)

# Send media from a URL
result = api.send_message(
    number="1234567890",
    message="Check out this remote image!",
    media_url="https://example.com/image.jpg",
    message_id="msg_004"
)
```

### Check a Profile

```python
profile = api.check_profile("1234567890")
if profile["ok"] and profile["exists"]:
    print(f"Number exists on WhatsApp: {profile['number']}")
    print(f"Profile picture: {profile.get('profilePicUrl')}")
    print(f"Status: {profile.get('statusText')}")
```

### Track a Message

```python
# Track a message
api.track_message(
    message_id="msg_001",
    phone_number="1234567890",
    content="Hello from WhatsApp API!"
)

# Get message status
status = api.get_message_details("msg_001")
```

### Multi-Account Support

```python
# Start all accounts
api.start_all_accounts()

# Switch between accounts
api.set_account("acc2")

# Send from specific account
api.send_message(
    number="1234567890",
    message="Hello from Account 3!",
    account="acc3"
)
```

## Troubleshooting

### Server Won't Start

- Check if the port is already in use
- Ensure Node.js is installed (v14 or later)
- Check for errors in the console output

### Can't Connect to WhatsApp

- Make sure you're scanning the QR code with the correct WhatsApp account
- Check if the QR code has expired (get a new one)
- Ensure your WhatsApp app is up to date

### API Calls Failing

- Check if the server is running
- Verify the API host URL is correct
- Check if API key authentication is enabled and configured correctly

### Messages Not Sending

- Ensure the account is connected
- Verify the phone number format is correct
- Check if the message content is valid
