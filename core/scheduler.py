"""
Clock-Aligned Background Scheduler for AI Gold Scalper Web Dashboard
Calculates next clock boundary + 3 seconds buffer, and runs background cycles.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable


# Available intervals
INTERVAL_MINUTES_MAP = {
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "3h": 180,
    "4h": 240,
}

INTERVAL_LABELS = {
    "5m": "5 Minutes",
    "15m": "15 Minutes",
    "30m": "30 Minutes",
    "1h": "1 Hour",
    "2h": "2 Hours",
    "3h": "3 Hours",
    "4h": "4 Hours",
}

DEFAULT_BUFFER_SECONDS = 3


def calculate_next_aligned_time(
    interval_minutes: int,
    buffer_seconds: int = DEFAULT_BUFFER_SECONDS,
    now: Optional[datetime] = None
) -> datetime:
    """
    Calculates the next clock boundary aligned to interval_minutes + buffer_seconds.

    Buffer = 3s ensures candles have fully closed in MT5 and accounts for 1-2s server/local clock skew:
      - For 15 mins at 11:14:59 -> next boundary 11:15, +3s -> 11:15:03.
      - For 15 mins at 11:15:03 -> next boundary 11:30, +3s -> 11:30:03.
      - For 5 mins at 11:09:59  -> next boundary 11:10, +3s -> 11:10:03.
      - For 1 hour at 11:59:59  -> next boundary 12:00, +3s -> 12:00:03.
    """
    if now is None:
        now = datetime.now()

    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_from_day_start = (now - day_start).total_seconds()
    interval_seconds = interval_minutes * 60
    slot = int((seconds_from_day_start - buffer_seconds) // interval_seconds) + 1
    target = day_start + timedelta(seconds=slot * interval_seconds + buffer_seconds)

    if target <= now:
        target += timedelta(minutes=interval_minutes)

    return target


class GoldScheduler:
    def __init__(self, callback_task: Callable[[], None]):
        self.callback_task = callback_task
        self.lock = threading.Lock()
        self.is_enabled = False  # Default: OFF
        self.interval_key = "5m"
        self.next_run_time: Optional[datetime] = None
        self.last_run_time: Optional[datetime] = None
        self.is_busy = False
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def set_enabled(self, enabled: bool) -> Dict[str, Any]:
        with self.lock:
            old_state = self.is_enabled
            self.is_enabled = enabled

            if enabled:
                # When switched to ON: Trigger immediate run, then set next aligned time
                interval_mins = INTERVAL_MINUTES_MAP.get(self.interval_key, 5)
                self.next_run_time = calculate_next_aligned_time(interval_mins, buffer_seconds=DEFAULT_BUFFER_SECONDS)
                # Spawn immediate run in separate thread so API doesn't block
                threading.Thread(target=self._run_job_now, daemon=True).start()
            else:
                self.next_run_time = None

        return self.get_status()

    def set_interval(self, interval_key: str) -> Dict[str, Any]:
        with self.lock:
            if interval_key in INTERVAL_MINUTES_MAP:
                self.interval_key = interval_key
                if self.is_enabled:
                    interval_mins = INTERVAL_MINUTES_MAP[interval_key]
                    self.next_run_time = calculate_next_aligned_time(interval_mins, buffer_seconds=DEFAULT_BUFFER_SECONDS)

        return self.get_status()

    def trigger_immediate_run(self):
        """Triggers manual fetch and analyze now."""
        threading.Thread(target=self._run_job_now, daemon=True).start()

    def _run_job_now(self):
        if self.is_busy:
            return
        try:
            self.is_busy = True
            if self.callback_task:
                self.callback_task()
            with self.lock:
                self.last_run_time = datetime.now()
        except Exception as e:
            print(f"[Scheduler Error] Job execution failed: {e}")
        finally:
            self.is_busy = False

    def _worker_loop(self):
        while not self._stop_event.is_set():
            time.sleep(0.5)
            now = datetime.now()

            with self.lock:
                if self.is_enabled and self.next_run_time:
                    if now >= self.next_run_time and not self.is_busy:
                        # Schedule next target first
                        interval_mins = INTERVAL_MINUTES_MAP.get(self.interval_key, 5)
                        self.next_run_time = calculate_next_aligned_time(interval_mins, buffer_seconds=DEFAULT_BUFFER_SECONDS)
                        # Run job
                        threading.Thread(target=self._run_job_now, daemon=True).start()

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            now = datetime.now()
            remaining_seconds = 0
            if self.is_enabled and self.next_run_time:
                diff = (self.next_run_time - now).total_seconds()
                remaining_seconds = max(0, int(diff))

            next_run_str = self.next_run_time.strftime("%H:%M:%S") if self.next_run_time else "Off"
            last_run_str = self.last_run_time.strftime("%Y-%m-%d %H:%M:%S") if self.last_run_time else "None"

            return {
                "is_enabled": self.is_enabled,
                "interval_key": self.interval_key,
                "interval_label": INTERVAL_LABELS.get(self.interval_key, "5 Minutes"),
                "available_intervals": [
                    {"key": k, "label": v} for k, v in INTERVAL_LABELS.items()
                ],
                "next_run_time": next_run_str,
                "next_run_seconds": remaining_seconds,
                "last_run_time": last_run_str,
                "is_busy": self.is_busy
            }
