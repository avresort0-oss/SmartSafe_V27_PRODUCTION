#!/usr/bin/env python3
"""
SmartSafe V27 - GUI Test Script
Tests if the GUI can start without issues
"""

import sys
import logging
import traceback

# Set up basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test all GUI-related imports"""
    try:
        logger.info("Testing imports...")
        import customtkinter as ctk

        logger.info("✓ customtkinter")

        import tkinter as tk

        logger.info("✓ tkinter")

        # Test main imports
        import main

        logger.info("✓ main module")

        from core.config import SETTINGS

        logger.info("✓ core.config")

        return True
    except Exception as e:
        logger.error(f"Import failed: {e}")
        traceback.print_exc()
        return False


def test_gui_creation():
    """Test GUI creation without showing window"""
    try:
        logger.info("Testing GUI creation...")
        import main

        # Create app instance (don't show window)
        app = main.SmartSafeProduction()

        # Test that it was created
        assert hasattr(app, "title")
        assert hasattr(app, "mainloop")

        logger.info("✓ GUI instance created successfully")
        return True

    except Exception as e:
        logger.error(f"GUI creation failed: {e}")
        traceback.print_exc()
        return False


def main():
    logger.info("=" * 50)
    logger.info("SmartSafe V27 GUI Test")
    logger.info("=" * 50)

    success = True

    if not test_imports():
        success = False

    if not test_gui_creation():
        success = False

    logger.info("=" * 50)
    if success:
        logger.info("✅ All GUI tests passed!")
        logger.info("The GUI should work when started normally.")
    else:
        logger.error("❌ GUI tests failed!")
        logger.error("Check the error messages above.")
    logger.info("=" * 50)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
