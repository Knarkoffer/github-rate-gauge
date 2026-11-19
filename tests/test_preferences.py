import ctypes
from datetime import datetime
import gc
import json
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import preferences
from preferences import Preferences, PreferencesStore, clamp_position
import rate_gauge


class PreferencesStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = PreferencesStore(Path(directory.name) / "settings.json")

    def test_missing_and_invalid_settings_use_defaults(self):
        self.assertEqual(self.store.load(), Preferences())
        for value in (
            "invalid json",
            "[]",
            '{"position": [true, 20]}',
            '{"position": [0, 2147483648], "always_on_top": "false"}',
        ):
            with self.subTest(value=value):
                self.store.path.write_text(value, encoding="utf-8")
                self.assertEqual(self.store.load(), Preferences())

    def test_preferences_round_trip_with_negative_coordinates(self):
        expected = Preferences((-1400, -250), True)
        self.store.save(expected)
        self.assertEqual(self.store.load(), expected)
        self.assertEqual(
            json.loads(self.store.path.read_text()),
            {"position": [-1400, -250], "always_on_top": True},
        )

    def test_invalid_position_preserves_valid_topmost_setting(self):
        self.store.path.write_text(
            '{"position": "invalid", "always_on_top": true}', encoding="utf-8"
        )
        self.assertEqual(self.store.load(), Preferences(always_on_top=True))

    def test_failed_atomic_write_preserves_previous_settings(self):
        expected = Preferences((100, 200), True)
        self.store.save(expected)
        with patch("preferences.os.replace", side_effect=OSError("Write failed")):
            with self.assertRaises(OSError):
                self.store.save(Preferences((500, 600), False))
        self.assertEqual(self.store.load(), expected)
        self.assertEqual(list(self.store.path.parent.iterdir()), [self.store.path])

    def test_default_file_is_in_local_appdata(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": str(self.store.path.parent)}):
            self.assertEqual(
                PreferencesStore().path,
                self.store.path.parent / "GitHubRateGauge" / "settings.json",
            )


class MonitorPositionTests(unittest.TestCase):
    def test_position_on_negative_coordinate_monitor_is_preserved(self):
        self.assertEqual(
            clamp_position((-1600, -500), (900, 500), (-1920, -1080, 0, 0)),
            (-1600, -500),
        )

    def test_removed_monitor_position_moves_into_work_area(self):
        self.assertEqual(
            clamp_position((4000, -1200), (900, 500), (0, 0, 1920, 1040)),
            (1020, 0),
        )

    def test_oversized_window_keeps_its_top_left_accessible(self):
        self.assertEqual(
            clamp_position((2000, 500), (1800, 1000), (0, 0, 1280, 720)),
            (0, 0),
        )


@unittest.skipUnless(os.name == "nt", "Requires native Windows window positioning")
class WindowPreferencesTests(unittest.TestCase):
    def setUp(self):
        # Tk objects must be collected on the thread that created them.
        self.gc_was_enabled = gc.isenabled()
        gc.disable()
        self.addCleanup(self.collect_gui_objects)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = PreferencesStore(Path(directory.name) / "settings.json")

    def collect_gui_objects(self):
        gc.collect()
        if self.gc_was_enabled:
            gc.enable()

    def pump_until(self, root, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            root.update()
            time.sleep(0.01)
        self.assertTrue(predicate())

    def create_app(self):
        root = tk.Tk()
        quota = {key: (4500, 5000, datetime.now()) for key in ("core", "graphql")}
        with patch("rate_gauge.read_quota", return_value=quota):
            app = rate_gauge.RateGauge(root, preferences_store=self.store)
            self.addCleanup(self.close_app, app)
            self.pump_until(root, lambda: app.last_check is not None)
        return app

    def close_app(self, app):
        if app.closing:
            return
        thread = getattr(app.tray._icon, "_thread", None)
        for callback in app.root.tk.call("after", "info"):
            app.root.after_cancel(callback)
        app.close()
        if thread is not None:
            thread.join(timeout=5)

    def test_position_and_topmost_are_restored_after_relaunch(self):
        app = self.create_app()
        preferences.restore_window_position(app.root, (120, 140))
        app.root.update()
        expected = preferences.window_position(app.root)
        app.topmost_checkbox.invoke()
        self.pump_until(
            app.root, lambda: self.store.load() == Preferences(expected, True)
        )
        self.close_app(app)

        reopened = self.create_app()
        self.assertEqual(preferences.window_position(reopened.root), expected)
        self.assertTrue(reopened.always_on_top.get())
        self.assertTrue(reopened.root.attributes("-topmost"))

    def test_quit_from_tray_keeps_last_visible_position(self):
        app = self.create_app()
        preferences.restore_window_position(app.root, (180, 220))
        app.root.update()
        expected = preferences.window_position(app.root)
        with patch.object(app.tray._icon, "notify"):
            app.root.iconify()
            self.pump_until(
                app.root,
                lambda: app.root.state() == "withdrawn" and app.tray._icon.visible,
            )
        self.close_app(app)
        self.assertEqual(self.store.load().position, expected)

    def test_offscreen_saved_position_is_clamped_to_monitor(self):
        self.store.save(Preferences((2_000_000_000, -2_000_000_000), True))
        app = self.create_app()
        user32 = preferences._windows_api()
        _, rectangle = preferences._native_window(app.root)
        monitor = user32.MonitorFromRect(ctypes.byref(rectangle), 2)
        info = preferences._MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        self.assertTrue(user32.GetMonitorInfoW(monitor, ctypes.byref(info)))
        self.assertGreaterEqual(rectangle.left, info.rcWork.left)
        self.assertGreaterEqual(rectangle.top, info.rcWork.top)
        self.assertLess(rectangle.left, info.rcWork.right)
        self.assertLess(rectangle.top, info.rcWork.bottom)
