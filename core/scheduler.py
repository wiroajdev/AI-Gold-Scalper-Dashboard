"""
Clock-Aligned Background Scheduler for AI Gold Scalper Web Dashboard
Calculates next clock boundary + 90 seconds buffer (1m30s), and runs background cycles.
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


def calculate_next_aligned_time(interval_minutes: int, buffer_seconds: int = 90) -> datetime:
    """
    Calculates the next clock boundary aligned to interval_minutes + buffer_seconds.

    Buffer = 90s (1m30s) ensures candles have fully closed and are committed before fetch:
      - M1 last bar closes at :00/:05/:10... wait 90s → fetch at :01:30/:06:30...
        Result: M1 latest bar = the :00/:05 bar (not the one before it).
    E.g. for 5 mins at 15:02:10  -> 15:05:30  ... wait, 15:06:30 with 90s buffer.
    For 5 mins at 15:02:10  -> next boundary 15:05, +90s -> 15:06:30.
    For 15 mins at 15:04:00 -> next boundary 15:15, +90s -> 15:16:30.
    For 1 hour at 15:04:00  -> next boundary 16:00, +90s -> 16:01:30.
    """
    now = datetime.now()

    if interval_minutes < 60:
        # Aligned to minute boundaries
        minute_slot = (now.minute // interval_minutes + 1) * interval_minutes
        if minute_slot >= 60:
            target_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            target = target_hour + timedelta(minutes=(minute_slot - 60), seconds=buffer_seconds)
        else:
            target = now.replace(minute=minute_slot, second=0, microsecond=0) + timedelta(seconds=buffer_seconds)
    else:
        # Aligned to hour boundaries (60, 120, 180, 240 mins)
        hours_step = interval_minutes // 60
        hour_slot = (now.hour // hours_step + 1) * hours_step
        if hour_slot >= 24:
            target_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            target = target_day + timedelta(hours=(hour_slot - 24), seconds=buffer_seconds)
        else:
            target = now.replace(hour=hour_slot, minute=0, second=0, microsecond=0) + timedelta(seconds=buffer_seconds)

    # In rare case where target <= now (e.g. current second is 15:05:31), add one full interval
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
                self.next_run_time = calculate_next_aligned_time(interval_mins, buffer_seconds=90)
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
                    self.next_run_time = calculate_next_aligned_time(interval_mins, buffer_seconds=90)

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
            time.sleep(1)
            now = datetime.now()

            with self.lock:
                if self.is_enabled and self.next_run_time:
                    if now >= self.next_run_time and not self.is_busy:
                        # Schedule next target first
                        interval_mins = INTERVAL_MINUTES_MAP.get(self.interval_key, 5)
                        self.next_run_time = calculate_next_aligned_time(interval_mins, buffer_seconds=90)
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
