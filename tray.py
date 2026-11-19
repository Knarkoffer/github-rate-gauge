"""Notification-area controls for the Windows gauge."""


class TrayController:
    def __init__(self, on_open, on_quit, icon_path):
        import pystray
        from PIL import Image

        self._on_open = on_open
        self._on_quit = on_quit
        self._started = False
        self._hint_shown = False
        with Image.open(icon_path) as image:
            icon_image = image.convert("RGBA")
        self._icon = pystray.Icon(
            "github_rate_gauge",
            icon_image,
            "GitHub Rate Gauge - Checking quota...",
            menu=pystray.Menu(
                pystray.MenuItem("Open", self._open, default=True),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def show(self):
        if self._started:
            self._icon.visible = True
        else:
            self._icon.run_detached()
            self._started = True

    def hide(self):
        if self._started:
            self._icon.visible = False

    def set_tooltip(self, text):
        self._icon.title = text[:127]

    def show_minimize_hint(self):
        if self._hint_shown:
            return
        self._hint_shown = True
        try:
            self._icon.notify(
                "Still running. Double-click the icon near the clock to reopen. "
                "Check the hidden icons arrow if you cannot see it.",
                "GitHub Rate Gauge",
            )
        except (AttributeError, NotImplementedError, OSError):
            pass

    def stop(self):
        if self._started:
            self._icon.stop()
            self._started = False

    def _open(self, _icon, _item):
        self._on_open()

    def _quit(self, _icon, _item):
        self._on_quit()
