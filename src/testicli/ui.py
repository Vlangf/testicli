"""Animated cat spinner for long-running operations."""

import threading
import time
from contextlib import contextmanager

from rich.console import Console
from rich.live import Live
from rich.text import Text

console = Console()

CAT_FRAMES = [
    r"""  /\_/\
 ( o.- )
  > ^ <
  /| |\
 (_| |_)""",
    r"""  /\_/\
 ( -.o )
  > ^ <
  /| |\
 (_| |_)""",
    r"""  /\_/\
 ( o.- )
  > ^ <
  /| |\
 (_| |_)""",
    r"""  /\_/\
 ( -.o )
  > ^ <
  /| |\
 (_| |_)""",
]

FRAME_INTERVAL = 0.3


@contextmanager
def cat_spinner(message: str):
    """Show an animated cat spinner while the wrapped code runs.

    Usage::

        with cat_spinner("Scanning project..."):
            do_long_running_work()
    """
    frame_index = 0
    stop_event = threading.Event()

    def _make_renderable(idx: int) -> Text:
        lines = CAT_FRAMES[idx % len(CAT_FRAMES)].splitlines()
        # Pad cat lines so message aligns nicely to the right
        padded = [f"  {line}" for line in lines]
        # Place message next to the middle line of the cat
        mid = len(padded) // 2
        padded[mid] += f"   {message}"
        return Text("\n".join(padded), style="blue")

    live = Live(
        _make_renderable(frame_index),
        console=console,
        transient=True,
        refresh_per_second=10,
    )

    def _animate():
        nonlocal frame_index
        while not stop_event.is_set():
            stop_event.wait(FRAME_INTERVAL)
            if stop_event.is_set():
                break
            frame_index += 1
            live.update(_make_renderable(frame_index))

    live.start()
    thread = threading.Thread(target=_animate, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join()
        live.stop()
