import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
import unittest
from unittest.mock import patch
from uuid import uuid4

import single_instance


class NonWindowsTests(unittest.TestCase):
    def test_non_windows_startup_is_supported(self):
        instance = single_instance.SingleInstance()
        with patch("single_instance.os.name", "posix"):
            self.assertTrue(instance.acquire())
            self.assertFalse(instance.activation_requested())
            instance.release()


@unittest.skipUnless(os.name == "nt", "Requires Windows named kernel objects")
class SingleInstanceTests(unittest.TestCase):
    def setUp(self):
        name = "Local\\GitHubRateGauge-Test-" + str(uuid4())
        self.names = patch.multiple(
            single_instance,
            MUTEX_NAME=name,
            ACTIVATION_EVENT_NAME=name + "-Activate",
            APPLICATION_TITLE=name,
        )
        self.names.start()
        self.addCleanup(self.names.stop)
        self.instance = single_instance.SingleInstance()
        self.addCleanup(self.instance.release)
        self.child_code = (
            "import os, sys\n"
            f"sys.path.insert(0, {str(Path(__file__).resolve().parent.parent)!r})\n"
            "import single_instance as module\n"
            f"module.MUTEX_NAME = {name!r}\n"
            f"module.ACTIVATION_EVENT_NAME = {name + '-Activate'!r}\n"
            f"module.APPLICATION_TITLE = {name!r}\n"
            "instance = module.SingleInstance()\n"
            "print(instance.acquire(), flush=True)\n"
        )

    def launch_again(self):
        result = subprocess.run(
            [sys.executable, "-c", self.child_code + "instance.release()\n"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_second_process_signals_the_first_and_exits(self):
        self.assertTrue(self.instance.acquire())
        self.assertEqual(self.launch_again(), "False")
        self.assertTrue(self.instance.activation_requested())
        self.assertFalse(self.instance.activation_requested())
        self.instance.release()
        self.assertEqual(self.launch_again(), "True")

    def test_second_process_does_not_wait_for_window_events(self):
        self.assertTrue(self.instance.acquire())
        root = tk.Tk()
        try:
            root.title(single_instance.APPLICATION_TITLE)
            root.update()
            root.withdraw()
            root.update()
            # The owner deliberately does not pump Tk events during the launch.
            self.assertEqual(self.launch_again(), "False")
            self.assertEqual(root.state(), "withdrawn")
            self.assertTrue(self.instance.activation_requested())
        finally:
            root.destroy()

    def test_crashed_process_does_not_leave_a_lock(self):
        owner = subprocess.Popen(
            [
                sys.executable,
                "-c",
                self.child_code + "sys.stdin.readline()\nos._exit(0)\n",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(owner.stdout.readline().strip(), "True")
            self.assertFalse(self.instance.acquire())
            owner.kill()
            owner.communicate(timeout=10)
            self.assertTrue(self.instance.acquire())
        finally:
            if owner.poll() is None:
                owner.kill()
            owner.communicate(timeout=10)
