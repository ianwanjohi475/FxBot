"""Weekly email performance report with equity curve image."""
import os
import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from datetime import datetime
import pytz
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class EmailReporter:
    def __init__(self):
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.sender = os.getenv("EMAIL_SENDER", "")
        self.password = os.getenv("EMAIL_PASSWORD", "")
        self.recipient = os.getenv("EMAIL_RECIPIENT", "")
        self.enabled = all([self.sender, self.password, self.recipient])
        if not self.enabled:
            logger.warning("[Email] Email credentials not set — reports disabled")

    def send_weekly_report(
        self,
        stats: dict,
        equity_curve_fig=None,
    ) -> bool:
        if not self.enabled:
            logger.info("[Email][DISABLED] Would send weekly report")
            return False

        subject = f"FxBot Weekly Report — {datetime.now(tz=pytz.utc).strftime('%Y-%m-%d')}"
        html_body = self._build_html_report(stats)

        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = self.recipient

        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)

        # Attach equity curve chart if provided
        if equity_curve_fig is not None:
            try:
                img_bytes = self._fig_to_png(equity_curve_fig)
                if img_bytes:
                    img_part = MIMEImage(img_bytes, name="equity_curve.png")
                    img_part.add_header("Content-ID", "<equity_curve>")
                    img_part.add_header("Content-Disposition", "inline")
                    msg.attach(img_part)
            except Exception as e:
                logger.warning(f"[Email] Chart attachment error: {e}")

        return self._send(msg)

    def _build_html_report(self, stats: dict) -> str:
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        total = wins + losses
        win_rate = f"{wins/total*100:.1f}%" if total > 0 else "N/A"
        pnl = stats.get("pnl_usd", 0)
        pnl_color = "green" if pnl >= 0 else "red"

        return f"""
        <html><body style="font-family:Arial,sans-serif;background:#1a1a2e;color:#eee;padding:20px;">
        <h2 style="color:#00d4ff;">📊 FxBot Weekly Performance Report</h2>
        <p style="color:#aaa;">Week ending {datetime.now(tz=pytz.utc).strftime('%Y-%m-%d')}</p>
        <table style="border-collapse:collapse;width:100%;max-width:500px;">
          <tr><td style="padding:8px;border:1px solid #333;">Total Trades</td>
              <td style="padding:8px;border:1px solid #333;"><b>{total}</b></td></tr>
          <tr><td style="padding:8px;border:1px solid #333;">Wins / Losses</td>
              <td style="padding:8px;border:1px solid #333;">{wins} / {losses}</td></tr>
          <tr><td style="padding:8px;border:1px solid #333;">Win Rate</td>
              <td style="padding:8px;border:1px solid #333;">{win_rate}</td></tr>
          <tr><td style="padding:8px;border:1px solid #333;">Net P&L</td>
              <td style="padding:8px;border:1px solid #333;color:{pnl_color};"><b>${pnl:+.2f}</b></td></tr>
          <tr><td style="padding:8px;border:1px solid #333;">Profit Factor</td>
              <td style="padding:8px;border:1px solid #333;">{stats.get('profit_factor', 0):.2f}</td></tr>
          <tr><td style="padding:8px;border:1px solid #333;">Max Drawdown</td>
              <td style="padding:8px;border:1px solid #333;">{stats.get('max_drawdown_pct', 0)*100:.1f}%</td></tr>
        </table>
        <br>
        <img src="cid:equity_curve" style="max-width:100%;border-radius:8px;" alt="Equity Curve"/>
        <p style="color:#666;font-size:12px;">FxBot — Automated Forex Trading System</p>
        </body></html>
        """

    def _fig_to_png(self, fig) -> Optional[bytes]:
        try:
            return fig.to_image(format="png", width=900, height=400)
        except Exception:
            try:
                import plotly.io as pio
                return pio.to_image(fig, format="png")
            except Exception as e:
                logger.error(f"[Email] Fig to PNG error: {e}")
                return None

    def _send(self, msg: MIMEMultipart) -> bool:
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender, self.password)
                server.sendmail(self.sender, self.recipient, msg.as_string())
            logger.info(f"[Email] Report sent to {self.recipient}")
            return True
        except Exception as e:
            logger.error(f"[Email] Send error: {e}")
            return False
