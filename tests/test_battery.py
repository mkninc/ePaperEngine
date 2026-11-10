"""The battery entities: what counts as a reading, and what they are called.

Two things are held here.

**A reading is only a reading while the probe says so.** ``battery.py`` feeds a
sensor that exists to switch a charger. A level kept from a probe that has since
failed would let an automation act on a number nobody measured, so every way
the probe can fall silent has to end in ``None`` — which the entities show as
``unavailable``.

**The documented entity IDs are the ones Home Assistant creates.** An ID is
derived from the entity's *name*, not from its translation key. A key that
drifts from its English name therefore produces documentation — and automation
examples — for an entity that does not exist. Nothing else catches that: the
integration runs fine, only the copied YAML does nothing.

Pure stdlib: ``battery.py`` imports no ``homeassistant``, and the naming half
reads the sources and catalogs.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import unicodedata
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = REPO_ROOT / "custom_components" / "epaperengine"
DOCS = REPO_ROOT / "docs"

ENTITY_PLATFORMS = ("sensor", "binary_sensor", "button")
DEVICE = "epaperengine"


def _load_battery():
    spec = importlib.util.spec_from_file_location("epe_battery", COMPONENT / "battery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


battery = _load_battery()


def _probe(**battery_fields) -> dict:
    """An answered probe, as ``AddonClient.async_display`` hands it over."""
    return {
        "addon": True,
        "reachable": True,
        "host": "192.0.2.10",
        "battery": dict(battery_fields),
    }


class TestBatteryPercent(unittest.TestCase):
    def test_an_answered_probe_gives_the_level(self) -> None:
        self.assertEqual(battery.battery_percent(_probe(batteryPercent=67)), 67)

    def test_the_ends_of_the_scale_are_readings(self) -> None:
        """0 is falsy — the one value a careless ``or`` would throw away, and
        the one a charger automation most needs to see."""
        self.assertEqual(battery.battery_percent(_probe(batteryPercent=0)), 0)
        self.assertEqual(battery.battery_percent(_probe(batteryPercent=100)), 100)

    def test_a_fraction_is_rounded(self) -> None:
        self.assertEqual(battery.battery_percent(_probe(batteryPercent=66.6)), 67)

    def test_no_probe_yet_is_no_reading(self) -> None:
        self.assertIsNone(battery.battery_percent({}))
        self.assertIsNone(battery.battery_percent(None))

    def test_a_mute_addon_is_no_reading(self) -> None:
        display = {"reachable": False, "error": "timeout", "addon": False}
        self.assertIsNone(battery.battery_percent(display))

    def test_an_unreachable_panel_is_no_reading(self) -> None:
        display = {"addon": True, "reachable": False, "error": "ECONNREFUSED"}
        self.assertIsNone(battery.battery_percent(display))

    def test_a_stale_block_on_a_failed_probe_is_ignored(self) -> None:
        """The add-on does not send one today. If it ever kept the last block
        around, this is the line that keeps it off the sensor."""
        display = _probe(batteryPercent=67)
        display["reachable"] = False
        self.assertIsNone(battery.battery_percent(display))

    def test_a_refused_battery_command_is_no_reading(self) -> None:
        """``probe.mjs`` records a failing getter as ``null`` and carries on:
        the panel is reachable, the battery row is blank."""
        display = _probe()
        display["battery"] = None
        self.assertIsNone(battery.battery_percent(display))
        self.assertIsNone(battery.battery_percent(_probe()))

    def test_what_is_not_a_percentage_is_no_reading(self) -> None:
        for value in (True, "67", None, -1, 101, 255, float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertIsNone(battery.battery_percent(_probe(batteryPercent=value)))


class TestChargerConnected(unittest.TestCase):
    def test_an_answered_probe_gives_the_state(self) -> None:
        self.assertIs(battery.charger_connected(_probe(pluggedIn=True)), True)
        self.assertIs(battery.charger_connected(_probe(pluggedIn=False)), False)

    def test_unplugged_is_an_answer_not_a_gap(self) -> None:
        """``False`` must stay ``False`` — "off", not ``unavailable``."""
        self.assertIsNotNone(battery.charger_connected(_probe(pluggedIn=False)))

    def test_only_a_boolean_counts(self) -> None:
        for value in ("false", "true", 0, 1, None):
            with self.subTest(value=value):
                self.assertIsNone(battery.charger_connected(_probe(pluggedIn=value)))

    def test_a_silent_probe_says_nothing(self) -> None:
        for display in (
            {},
            None,
            {"reachable": False, "error": "timeout", "addon": False},
            {"addon": True, "reachable": False, "battery": {"pluggedIn": True}},
            {"addon": True, "reachable": True, "battery": None},
        ):
            with self.subTest(display=display):
                self.assertIsNone(battery.charger_connected(display))


def _slug(name: str) -> str:
    """Home Assistant's ``slugify``, near enough for these names."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", plain.lower()).strip("_")


def _entity_names(catalog: str) -> dict[tuple[str, str], str]:
    """``(platform, translation_key)`` → name, from one catalog."""
    entities = json.loads((COMPONENT / catalog).read_text(encoding="utf-8"))["entity"]
    return {
        (platform, key): entry["name"]
        for platform in ENTITY_PLATFORMS
        for key, entry in entities.get(platform, {}).items()
    }


class TestEntityIds(unittest.TestCase):
    def test_the_battery_entities_are_in_the_catalog(self) -> None:
        names = _entity_names("strings.json")
        self.assertIn(("sensor", "battery"), names)
        self.assertIn(("binary_sensor", "charger_connected"), names)

    def test_every_translation_key_is_the_slug_of_its_english_name(self) -> None:
        """So that ``<platform>.epaperengine_<key>`` is the ID an English
        installation gets, and the key can be trusted when writing docs."""
        for (platform, key), name in _entity_names("strings.json").items():
            self.assertEqual(
                _slug(name), key,
                f"{platform}.{key!r} is named {name!r}: Home Assistant will "
                f"create {platform}.{DEVICE}_{_slug(name)}",
            )

    def test_every_entity_id_in_the_docs_exists(self) -> None:
        """English IDs, plus the German ones the docs quote as an example."""
        known = {
            f"{platform}.{DEVICE}_{_slug(name)}"
            for catalog in ("strings.json", "translations/de.json")
            for (platform, _key), name in _entity_names(catalog).items()
        }
        pattern = re.compile(
            rf"\b({'|'.join(ENTITY_PLATFORMS)})\.{DEVICE}_[a-z0-9_]+"
        )
        found = 0
        for page in sorted(DOCS.glob("*.md")):
            for match in pattern.finditer(page.read_text(encoding="utf-8")):
                found += 1
                self.assertIn(
                    match.group(0), known,
                    f"{page.name} names {match.group(0)}, which no entity produces",
                )
        self.assertTrue(found, "no entity IDs found in docs — pattern broken?")


if __name__ == "__main__":
    unittest.main()
