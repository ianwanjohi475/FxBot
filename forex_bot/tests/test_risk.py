"""Tests for risk management."""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.position_sizing import PositionSizer
from risk.stop_loss import StopLossCalculator
from risk.take_profit import TakeProfitCalculator
from risk.trailing_stop import TrailingStop
from risk.drawdown_control import DrawdownController
from risk.correlation_filter import CorrelationFilter


class TestPositionSizer:
    def setup_method(self):
        self.sizer = PositionSizer(risk_pct=0.01)

    def test_calculate_lot_size_basic(self):
        lot = self.sizer.calculate_lot_size(10000, 1.1000, 1.0900, "EUR_USD")
        assert lot > 0
        assert lot <= 10.0  # Sanity check

    def test_calculate_lot_size_jpy(self):
        lot = self.sizer.calculate_lot_size(10000, 150.00, 149.00, "USD_JPY")
        assert lot > 0

    def test_account_size_type(self):
        assert self.sizer.get_account_size_type(500) == "nano"
        assert self.sizer.get_account_size_type(5000) == "micro"
        assert self.sizer.get_account_size_type(50000) == "standard"

    def test_adjust_for_drawdown(self):
        lot = self.sizer.adjust_for_drawdown(0.10, 0.04)
        assert lot == pytest.approx(0.05, abs=0.001)

    def test_no_adjust_small_drawdown(self):
        lot = self.sizer.adjust_for_drawdown(0.10, 0.02)
        assert lot == pytest.approx(0.10)

    def test_zero_sl_returns_min(self):
        lot = self.sizer.calculate_lot_size(10000, 1.1000, 1.1000, "EUR_USD")
        assert lot >= 0.001


class TestStopLossCalculator:
    def setup_method(self):
        self.calc = StopLossCalculator()

    def test_atr_based_sl_buy(self):
        sl = self.calc.atr_based_sl(1.1000, "BUY", 0.0010)
        assert sl < 1.1000
        assert sl == pytest.approx(1.1000 - 0.0015, abs=0.00001)

    def test_atr_based_sl_sell(self):
        sl = self.calc.atr_based_sl(1.1000, "SELL", 0.0010)
        assert sl > 1.1000

    def test_fixed_pip_sl(self):
        sl = self.calc.fixed_pip_sl(1.1000, "BUY", 20, "EUR_USD")
        assert sl == pytest.approx(1.1000 - 20 * 0.0001, abs=0.00001)

    def test_validate_sl_too_tight(self):
        sl = self.calc.validate_sl(1.1000, 1.0999, "BUY", min_pips=5)
        assert abs(1.1000 - sl) >= 5 * 0.0001

    def test_validate_sl_too_wide(self):
        sl = self.calc.validate_sl(1.1000, 1.0700, "BUY", max_pips=100)
        assert abs(1.1000 - sl) <= 100 * 0.0001


class TestTakeProfitCalculator:
    def setup_method(self):
        self.calc = TakeProfitCalculator()

    def test_tp_levels_buy(self):
        tp1, tp2, tp3 = self.calc.calculate_tp_levels(1.1000, 1.0950, "BUY")
        assert tp1 > 1.1000
        assert tp2 > tp1
        assert tp3 > tp2

    def test_tp_levels_sell(self):
        tp1, tp2, tp3 = self.calc.calculate_tp_levels(1.1000, 1.1050, "SELL")
        assert tp1 < 1.1000
        assert tp2 < tp1
        assert tp3 < tp2

    def test_rr_ratios(self):
        risk = 0.0050
        tp1, tp2, tp3 = self.calc.calculate_tp_levels(1.1000, 1.1000 - risk, "BUY",
                                                        rr_tp1=1.0, rr_tp2=2.0, rr_tp3=3.0)
        assert tp1 == pytest.approx(1.1000 + risk * 1.0, abs=0.0001)
        assert tp2 == pytest.approx(1.1000 + risk * 2.0, abs=0.0001)
        assert tp3 == pytest.approx(1.1000 + risk * 3.0, abs=0.0001)

    def test_partial_close_plan(self):
        plan = self.calc.partial_close_plan()
        assert len(plan) == 3
        total_pct = sum(p for _, p in plan)
        assert total_pct == pytest.approx(1.0)


class TestTrailingStop:
    def setup_method(self):
        self.ts = TrailingStop()

    def test_activate_and_update_buy(self):
        self.ts.activate("T1", 1.1000, "BUY", 0.0010, 1.1015)
        new_sl = self.ts.update("T1", 1.1015, 0.0010)
        assert new_sl is None or new_sl < 1.1015  # Activating

    def test_get_current_sl(self):
        self.ts.activate("T2", 1.1000, "BUY", 0.0010, 1.1015)
        sl = self.ts.get_current_sl("T2")
        assert sl is not None

    def test_deactivate(self):
        self.ts.activate("T3", 1.1000, "SELL", 0.0010, 1.0985)
        self.ts.deactivate("T3")
        assert self.ts.get_current_sl("T3") is None


class TestDrawdownController:
    def setup_method(self):
        self.dc = DrawdownController(max_daily_loss=0.05, max_weekly_loss=0.10)

    def test_daily_drawdown(self):
        self.dc.update_balance(10000)
        dd = self.dc.get_daily_drawdown_pct(9500)
        assert dd == pytest.approx(0.05)

    def test_should_stop_daily(self):
        self.dc.update_balance(10000)
        assert self.dc.should_stop_trading_today(9499) is True
        assert self.dc.should_stop_trading_today(9600) is False

    def test_consecutive_losses(self):
        self.dc.register_loss()
        self.dc.register_loss()
        assert self.dc.should_pause_after_losses() is False
        self.dc.register_loss()
        assert self.dc.should_pause_after_losses() is True

    def test_register_win_resets_losses(self):
        self.dc.register_loss()
        self.dc.register_loss()
        self.dc.register_loss()
        self.dc.register_win()
        assert self.dc.consecutive_losses == 0

    def test_position_size_multiplier(self):
        self.dc.update_balance(10000)
        assert self.dc.get_position_size_multiplier(9700) == pytest.approx(0.5)
        assert self.dc.get_position_size_multiplier(9800) == pytest.approx(1.0)


class TestCorrelationFilter:
    def setup_method(self):
        self.cf = CorrelationFilter()

    def test_can_open_uncorrelated(self):
        allowed, _ = self.cf.can_open_trade("USD_JPY", "BUY")
        assert allowed is True

    def test_blocks_correlated_same_direction(self):
        self.cf.add_trade("EUR_USD", "BUY")
        allowed, reason = self.cf.can_open_trade("GBP_USD", "BUY")
        assert allowed is False

    def test_allows_correlated_opposite_direction(self):
        self.cf.add_trade("EUR_USD", "BUY")
        allowed, _ = self.cf.can_open_trade("GBP_USD", "SELL")
        assert allowed is True

    def test_remove_trade(self):
        self.cf.add_trade("EUR_USD", "BUY")
        self.cf.remove_trade("EUR_USD")
        allowed, _ = self.cf.can_open_trade("GBP_USD", "BUY")
        assert allowed is True
