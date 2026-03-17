import sys
import subprocess
import importlib.util
import os

def check_package(package_name, import_name=None):
    if import_name is None:
        import_name = package_name
    
    print(f"Checking {package_name}...", end=" ")
    
    if importlib.util.find_spec(import_name):
        print("OK")
        return True
    else:
        print("MISSING")
        return False

def install_package(package_name):
    print(f"Installing {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"OK: {package_name} installed successfully")
        return True
    except subprocess.CalledProcessError:
        print(f"FAILED: Could not install {package_name}")
        return False

def main():
    print("="*50)
    print("SmartSafe V27 - System Verification Tool")
    print("="*50)
    
    # List of (pip_package_name, import_name)
    required_packages = [
        ("customtkinter", "customtkinter"),
        ("requests", "requests"),
        ("Pillow", "PIL"),
        ("qrcode[pil]", "qrcode"),
        ("openpyxl", "openpyxl"),  # For Excel support
        ("pandas", "pandas"),      # For advanced data handling
        ("setuptools", "setuptools"),  # distutils compatibility for GUI libs on Py3.14+
        ("numpy", "numpy"),        # ML feature vector math
        ("scikit-learn", "sklearn"),  # ML risk engine models
        ("python-dotenv", "dotenv"),  # For .env-based configuration
        ("fastapi", "fastapi"),    # For Webhook API
        ("uvicorn", "uvicorn"),    # For Webhook Server
        ("psycopg2-binary", "psycopg2"), # For PostgreSQL Support
    ]
    
    unresolved_missing = 0
    for package, import_name in required_packages:
        if not check_package(package, import_name):
            if not install_package(package):
                unresolved_missing += 1
            else:
                # Re-check import after install in case installation failed silently.
                if not check_package(package, import_name):
                    unresolved_missing += 1
            
    print("\n" + "="*50)
    if unresolved_missing == 0:
        print("All systems operational. You can run 'main.py' now.")
    else:
        print("Verification finished, but some dependencies are still missing.")
    print("="*50)
    no_pause = os.getenv("SMARTSAFE_NO_PAUSE", "").strip() == "1"
    try:
        if (not no_pause) and sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to exit...")
    except EOFError:
        pass
    return 0 if unresolved_missing == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
