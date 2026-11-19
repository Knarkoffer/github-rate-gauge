"""Show GitHub REST and GraphQL quota usage for the active gh CLI login."""

import argparse
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path

from tray import TrayController

REFRESH_MS = 60_000
BACKGROUND = "#c0c0c0"
INK = "#000000"
PAPER = "#ffffff"
GH_COMMAND = ["gh"]
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT
if not (DATA_ROOT / "VERSION").is_file():
    DATA_ROOT = Path(sys.prefix) / "share" / "github-rate-gauge"
__version__ = (DATA_ROOT / "VERSION").read_text(encoding="utf-8").strip()
VERSION_LABEL = f"Version {__version__}"


def read_quota():
    result = subprocess.run(
        [*GH_COMMAND, "api", "rate_limit", "--jq", ".resources"],
        capture_output=True,
        text=True,
        timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "GitHub CLI request failed.")
    data = json.loads(result.stdout)
    return {
        resource: (
            data[resource]["remaining"],
            data[resource]["limit"],
            datetime.fromtimestamp(data[resource]["reset"]),
        )
        for resource in ("core", "graphql")
    }


class QuotaGauge(tk.LabelFrame):
    def __init__(self, parent, title, unit, family):
        super().__init__(parent, text=title, padx=10, pady=8, relief=tk.GROOVE)
        self.unit = unit
        self.used = None
        self.canvas = tk.Canvas(
            self,
            width=400,
            height=230,
            bg=PAPER,
            relief=tk.SUNKEN,
            borderwidth=2,
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.create_text(
            200, 24, text=f"{unit.upper()} USED (%)", fill=INK, font=(family, 9, "bold")
        )
        for start, extent, color in [
            (72, 108, "#7d9685"),
            (36, 36, "#b39a68"),
            (0, 36, "#b47d78"),
        ]:
            self.canvas.create_arc(
                60,
                60,
                340,
                340,
                start=start,
                extent=extent,
                style=tk.ARC,
                outline=color,
                width=8,
            )
        for percent in range(0, 101, 5):
            angle = math.pi * (1 - percent / 100)
            inner = 124 if percent % 20 == 0 else 132
            self.canvas.create_line(
                200 + inner * math.cos(angle),
                200 - inner * math.sin(angle),
                200 + 143 * math.cos(angle),
                200 - 143 * math.sin(angle),
                fill=INK,
                width=1,
            )
            if percent % 20 == 0:
                self.canvas.create_text(
                    200 + 162 * math.cos(angle),
                    200 - 162 * math.sin(angle),
                    text=str(percent),
                    fill=INK,
                    font=(family, 9),
                )
        self.count = tk.Label(
            self,
            text="Reading quota...",
            bg=PAPER,
            fg=INK,
            relief=tk.SUNKEN,
            padx=6,
            pady=5,
            font=("Courier", 15, "bold"),
        )
        self.count.pack(fill=tk.X, pady=(10, 4))
        self.remaining = tk.Label(self)
        self.remaining.pack(pady=(4, 0))
        self.reset = tk.Label(self)
        self.reset.pack(pady=(4, 0))

    def display(self, remaining, limit, reset):
        used = limit - remaining
        self.used = used
        self.canvas.delete("needle")
        if limit > 0:
            fraction = max(0, min(1, used / limit))
            angle = math.pi * (1 - fraction)
            x = 200 + 117 * math.cos(angle)
            y = 200 - 117 * math.sin(angle)
            self.canvas.create_line(
                200, 200, x, y, fill=INK, width=3, arrow=tk.LAST, tags="needle"
            )
            self.canvas.create_rectangle(
                195, 195, 205, 205, fill=INK, outline=INK, tags="needle"
            )
        self.count.configure(text=f"{used:,} of {limit:,} used")
        self.remaining.configure(text=f"{remaining:,} {self.unit} remaining")
        self.reset.configure(text=f"Resets {reset:%d %b at %H:%M:%S} (local time)")


class RateGauge:
    def __init__(self, root):
        self.root = root
        root.title("GitHub rate gauge")
        if os.name == "nt":
            root.iconbitmap(str(DATA_ROOT / "assets" / "gauge.ico"))
        else:
            self.icon = tk.PhotoImage(file=DATA_ROOT / "assets" / "gauge.png")
            root.iconphoto(True, self.icon)
        root.configure(bg=BACKGROUND)
        root.resizable(False, False)
        families = set(tkfont.families(root))
        family = next(
            (
                name
                for name in ("MS Sans Serif", "Tahoma", "Liberation Sans")
                if name in families
            ),
            "TkDefaultFont",
        )
        root.option_add("*Font", (family, 9))
        root.option_add("*Background", BACKGROUND)
        root.option_add("*Foreground", INK)
        root.option_add("*highlightThickness", 0)
        root.option_add("*BorderWidth", 2)
        root.option_add("*activeBackground", BACKGROUND)
        root.option_add("*activeForeground", INK)
        self.results = queue.Queue()
        self.timer = None
        self.last_check = None
        self.closing = False
        self.tray_actions = queue.SimpleQueue()
        self.tray = None
        if os.name == "nt":
            self.tray = TrayController(
                lambda: self.tray_actions.put(self.restore),
                lambda: self.tray_actions.put(self.close),
                DATA_ROOT / "assets" / "gauge.png",
            )
            root.bind("<Unmap>", self.window_unmapped, add="+")
            root.after(100, self.poll_tray_actions)
        root.protocol("WM_DELETE_WINDOW", self.close)

        panel = tk.Frame(root, relief=tk.RAISED, borderwidth=2)
        panel.pack(fill=tk.BOTH, expand=True)
        meters = tk.Frame(panel)
        meters.pack(padx=10, pady=(10, 8))
        self.gauges = {}
        for resource, title, unit in (
            ("core", "REST API", "requests"),
            ("graphql", "GraphQL API", "points"),
        ):
            gauge = QuotaGauge(meters, title, unit, family)
            gauge.pack(side=tk.LEFT, padx=4)
            self.gauges[resource] = gauge
        controls = tk.Frame(panel)
        controls.pack(fill=tk.X, padx=12, pady=(0, 10))
        self.always_on_top = tk.BooleanVar(root, value=False)
        self.topmost_checkbox = tk.Checkbutton(
            controls,
            text="Always on top",
            variable=self.always_on_top,
            selectcolor=PAPER,
            command=lambda: root.attributes("-topmost", self.always_on_top.get()),
        )
        self.topmost_checkbox.pack(side=tk.LEFT)
        self.button = tk.Button(
            controls,
            text="Refresh now",
            command=self.refresh,
            underline=0,
            width=13,
            padx=8,
            pady=3,
            relief=tk.RAISED,
            overrelief=tk.RAISED,
            disabledforeground="#808080",
            default=tk.ACTIVE,
            highlightthickness=1,
            highlightbackground=BACKGROUND,
            highlightcolor=INK,
        )
        self.button.pack(side=tk.RIGHT)
        self.version = tk.Label(panel, text=VERSION_LABEL, anchor=tk.E, padx=6)
        self.version.pack(fill=tk.X, padx=3, pady=(0, 3))
        self.status = tk.Label(
            panel,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padx=5,
            pady=3,
            wraplength=840,
            justify=tk.LEFT,
        )
        self.status.pack(fill=tk.X, padx=3, pady=(0, 3))
        root.bind("<Alt-r>", lambda event: self.button.invoke())
        self.refresh()

    def window_unmapped(self, event):
        if event.widget is self.root:
            self.root.after_idle(self.hide_if_minimized)

    def hide_if_minimized(self):
        if not self.closing and self.root.state() == "iconic":
            self.tray.show()
            self.tray.show_minimize_hint()
            self.root.withdraw()

    def restore(self):
        if self.closing:
            return
        self.tray.hide()
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def poll_tray_actions(self):
        try:
            while not self.closing:
                self.tray_actions.get_nowait()()
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self.poll_tray_actions)

    def close(self):
        if self.closing:
            return
        self.closing = True
        if self.tray is not None:
            self.tray.stop()
        self.root.destroy()

    def update_tray_tooltip(self, failed):
        if self.tray is None:
            return
        lines = ["GitHub rate gauge"]
        for resource, label in (("core", "REST"), ("graphql", "GraphQL")):
            used = self.gauges[resource].used
            value = f"{used:,}" if used is not None else "Unavailable"
            lines.append(f"{label}: {value}")
        if failed:
            lines.append("Refresh failed")
        self.tray.set_tooltip("\n".join(lines))

    def refresh(self):
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.button.configure(state=tk.DISABLED)
        self.status.configure(text="Checking GitHub...")
        threading.Thread(target=self.fetch, daemon=True).start()
        self.root.after(100, self.receive)

    def fetch(self):
        try:
            self.results.put(read_quota())
        except FileNotFoundError:
            self.results.put("Install GitHub CLI (gh), then run gh auth login.")
        except (
            OSError,
            subprocess.TimeoutExpired,
            RuntimeError,
            ValueError,
            KeyError,
            TypeError,
            OverflowError,
        ) as error:
            self.results.put(str(error))

    def receive(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.receive)
            return
        if isinstance(result, str):
            if self.last_check is None:
                for gauge in self.gauges.values():
                    gauge.count.configure(text="Quota unavailable")
            previous = f"Last reading at {self.last_check}. " if self.last_check else ""
            self.status.configure(text=f"{previous}Refresh failed. {result}")
        else:
            for resource, values in result.items():
                self.gauges[resource].display(*values)
            self.last_check = datetime.now().strftime("%H:%M:%S")
            self.status.configure(
                text=f"Checked {self.last_check} | Updates every minute"
            )
        self.update_tray_tooltip(failed=isinstance(result, str))
        self.button.configure(state=tk.NORMAL)
        self.timer = self.root.after(REFRESH_MS, self.refresh)


def main():
    global GH_COMMAND

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wsl-distro",
        nargs="?",
        const="",
        help="Read quota using gh in WSL (default distribution if no name is given)",
    )
    args = parser.parse_args()
    distro = os.environ.get("WSL_DISTRO_NAME")
    if os.name != "nt" and distro:
        # Native Windows Tk lets the checkbox affect Windows desktop windows.
        venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
        windows_python = (
            str(venv_python) if venv_python.is_file() else shutil.which("python.exe")
        )
        if windows_python is None:
            parser.error(
                "Install Windows Python with Tkinter and add python.exe to PATH."
            )
        script = subprocess.check_output(
            ["wslpath", "-w", str(Path(__file__).resolve())], text=True
        ).strip()
        sys.exit(subprocess.call([windows_python, script, "--wsl-distro", distro]))
    if args.wsl_distro is not None:
        GH_COMMAND = ["wsl.exe"]
        if args.wsl_distro:
            GH_COMMAND.extend(["--distribution", args.wsl_distro])
        GH_COMMAND.extend(["--exec", "gh"])
    if os.name == "nt":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Knarkoffer.GitHubRateGauge"
        )
    window = tk.Tk()
    RateGauge(window)
    window.mainloop()


if __name__ == "__main__":
    sys.exit(main())
