import requests
import time
import sys

SERVER_URL = "http://localhost:4000"


def check_connection():
    print(f"Testing connection to WhatsApp Server at {SERVER_URL}...")

    try:
        # Try to hit the health endpoint
        start = time.time()
        response = requests.get(f"{SERVER_URL}/health", timeout=2)
        duration = (time.time() - start) * 1000

        if response.status_code == 200:
            print(f"[OK] SUCCESS: Server is online! (Latency: {duration:.0f}ms)")
            print(f"   Response: {response.text}")
            return True

        print(f"[WARN] Server reachable but returned {response.status_code}")
        return False

    except requests.exceptions.ConnectionError:
        print("[ERROR] Connection Refused")
        print("   The server is NOT running or the port is blocked.")
        print("\n   POSSIBLE FIXES:")
        print("   1. Run 'START_WHATSAPP_SERVER.bat' and keep that window open.")
        print("   2. Check if port 4000 is used by another app.")
        return False
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("SmartSafe V27 - Connection Diagnostic Tool")
    print("=" * 50)
    print("")

    check_connection()

    print("")
    print("=" * 50)
    try:
        if sys.stdin and sys.stdin.isatty():
            input("Press Enter to exit...")
    except EOFError:
        pass
