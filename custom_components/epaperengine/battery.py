"""What the last MDC probe says about the panel's battery.

Two questions, answered from the document ``GET /display`` returns: how full is
the battery, and is the charger connected. Both answer ``None`` whenever the
probe does not *currently* say so — the add-on is mute, the panel did not
answer, or it answered everything but ``getBatteryState``. The entities turn
``None`` into ``unavailable``.

That strictness is the point. These values exist to drive a charger on a smart
plug, and an automation must never switch on a reading from a probe that
failed: "67 %" from an hour ago is not a measurement.

No ``homeassistant`` import, so the tests can exercise it without an install.
"""

from __future__ import annotations

import math
from typing import Any


def _battery_block(display: Any) -> dict[str, Any]:
    """The ``battery`` object of an answered probe, else ``{}``."""
    if not isinstance(display, dict):
        return {}
    if display.get("addon") is False or display.get("reachable") is not True:
        return {}
    battery = display.get("battery")
    return battery if isinstance(battery, dict) else {}


def battery_percent(display: Any) -> int | None:
    """Charge level in percent, or ``None`` if the probe does not give one.

    Anything that is not a number from 0 to 100 is no reading: a sensor with
    device class ``battery`` showing 255 % would be believed.
    """
    value = _battery_block(display).get("batteryPercent")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return round(value)


def charger_connected(display: Any) -> bool | None:
    """Is the charger plugged in, or ``None`` if the probe does not say.

    Only a real boolean counts. ``bool("false")`` is ``True``, and "connected"
    is not the side to err on when the answer decides whether to keep charging.
    """
    value = _battery_block(display).get("pluggedIn")
    return value if isinstance(value, bool) else None
