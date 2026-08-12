"""Async emergency-alert pipeline: daily multi-source scans for the 10 demo
PIN codes, with Bedrock actionable insights.

Sources blended:
  1. Open-Meteo forecast (thunderstorm / heavy rain / wind)
  2. ICAR-NIVEDI disease catalogue (seasonal disease advisory)
  3. IMD public warnings (best-effort, often unavailable)
  4. wttr.in current conditions (severe weather classification)
"""

from __future__ import annotations

from .api import fetch_alert_feed
from .scan import scan_all_pins, scan_pin

__all__ = ["scan_all_pins", "scan_pin", "fetch_alert_feed"]
