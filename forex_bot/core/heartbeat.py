"""Bot heartbeat monitor — ensures the bot is alive."""
import threading
import time
from datetime import datetime
import pytz
from typing import Callable, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class HeartbeatMonitor:
    def __init__(self, interval: int = 30, on_failure: Callable = None):
        self.interval = interval
        self.on_failure = on_failure
        self.last_beat: Optional[datetime] = None
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._beat_count = 0

    def start(self):
        self.is_running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="HeartbeatThread"
        )
        self._thread.start()
        logger.info(f"[Heartbeat] Monitor started (interval={self.interval}s)")

    def stop(self):
        self.is_running = False
        logger.info("[Heartbeat] Monitor stopped")

    def _run(self):
        while self.is_running:
            self.beat()
            time.sleep(self.interval)

    def beat(self):
        self.last_beat = datetime.now(tz=pytz.utc)
        self._beat_count += 1
        logger.debug(f"[Heartbeat] Beat #{self._beat_count} at {self.last_beat.isoformat()}")

    def is_alive(self, max_seconds: int = None) -> bool:
        if self.last_beat is None:
            return False
        if max_seconds is None:
            max_seconds = self.interval * 3
        elapsed = (datetime.now(tz=pytz.utc) - self.last_beat).total_seconds()
        return elapsed < max_seconds

    def get_status(self) -> dict:
        return {
            "alive": self.is_alive(),
            "last_beat": self.last_beat.isoformat() if self.last_beat else None,
            "beat_count": self._beat_count,
            "interval": self.interval,
        }
