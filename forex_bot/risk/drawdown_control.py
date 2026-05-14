"""Drawdown control and consecutive-loss detection."""
from datetime import datetime, date
from typing import Optional
import pytz
from utils.logger import get_logger

logger = get_logger(__name__)


class DrawdownController:
    def __init__(self, max_daily_loss: float = 0.05, max_weekly_loss: float = 0.10):
        self.max_daily_loss = max_daily_loss
        self.max_weekly_loss = max_weekly_loss
        self.daily_start_balance: float = 0.0
        self.weekly_start_balance: float = 0.0
        self.peak_balance: float = 0.0
        self.consecutive_losses: int = 0
        self._last_daily_reset: Optional[date] = None
        self._last_weekly_reset: Optional[date] = None
        self._pause_until: Optional[datetime] = None

    def update_balance(self, balance: float, dt: datetime = None):
        if dt is None:
            dt = datetime.now(tz=pytz.utc)
        today = dt.date()

        if self._last_daily_reset is None or today > self._last_daily_reset:
            self.daily_start_balance = balance
            self._last_daily_reset = today

        week_start = today.isocalendar()[1]
        last_week = self._last_weekly_reset.isocalendar()[1] if self._last_weekly_reset else None
        if last_week is None or week_start != last_week:
            self.weekly_start_balance = balance
            self._last_weekly_reset = today

        if balance > self.peak_balance:
            self.peak_balance = balance

    def get_daily_drawdown_pct(self, current_balance: float) -> float:
        if self.daily_start_balance <= 0:
            return 0.0
        return (self.daily_start_balance - current_balance) / self.daily_start_balance

    def get_weekly_drawdown_pct(self, current_balance: float) -> float:
        if self.weekly_start_balance <= 0:
            return 0.0
        return (self.weekly_start_balance - current_balance) / self.weekly_start_balance

    def get_max_drawdown_pct(self, current_balance: float) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - current_balance) / self.peak_balance

    def should_stop_trading_today(self, current_balance: float) -> bool:
        dd = self.get_daily_drawdown_pct(current_balance)
        if dd >= self.max_daily_loss:
            logger.warning(f"[DrawdownControl] Daily loss limit hit: {dd:.2%}")
            return True
        return False

    def should_pause_until_monday(self, current_balance: float) -> bool:
        dd = self.get_weekly_drawdown_pct(current_balance)
        if dd >= self.max_weekly_loss:
            logger.warning(f"[DrawdownControl] Weekly loss limit hit: {dd:.2%}")
            return True
        return False

    def register_loss(self, dt: datetime = None):
        self.consecutive_losses += 1
        if self.consecutive_losses >= 3:
            self._pause_until = (dt or datetime.now(tz=pytz.utc)).replace(
                microsecond=0
            )
            from datetime import timedelta
            self._pause_until = self._pause_until + timedelta(hours=1)
            logger.warning(f"[DrawdownControl] 3 consecutive losses — pausing until {self._pause_until}")

    def register_win(self):
        self.consecutive_losses = 0

    def should_pause_after_losses(self, dt: datetime = None) -> bool:
        if self._pause_until is None:
            return False
        now = dt or datetime.now(tz=pytz.utc)
        if now < self._pause_until:
            return True
        self._pause_until = None
        self.consecutive_losses = 0
        return False

    def get_position_size_multiplier(self, current_balance: float) -> float:
        if self.get_daily_drawdown_pct(current_balance) > 0.03:
            return 0.5
        return 1.0

    def reset_daily(self, current_balance: float):
        self.daily_start_balance = current_balance
        self._last_daily_reset = datetime.now(tz=pytz.utc).date()

    def reset_weekly(self, current_balance: float):
        self.weekly_start_balance = current_balance
        self._last_weekly_reset = datetime.now(tz=pytz.utc).date()
