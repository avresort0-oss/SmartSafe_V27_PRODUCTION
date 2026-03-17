"""
Helpers for safe Tk UI updates from worker threads.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional


def ui_dispatch(widget, func: Callable[[], None]) -> None:
    """
    Dispatch a UI mutation to Tk main thread.
    """
    if widget is None:
        return

    try:
        exists = bool(widget.winfo_exists())
    except Exception:
        exists = False

    if not exists:
        return

    def _run():
        try:
            if widget.winfo_exists():
                func()
        except Exception:
            pass

    if threading.current_thread() is threading.main_thread():
        _run()
        return

    try:
        widget.after(0, _run)
    except Exception:
        pass


def start_daemon(target: Callable, *args, **kwargs) -> Optional[threading.Thread]:
    try:
        t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t
    except Exception:
        return None

