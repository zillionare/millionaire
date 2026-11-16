"""Exercise the installed native controller against its actual test service."""

import json
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from quantide.service.desktop_control import create_controller


def responsive():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8130/api/health", timeout=0.2) as response:
            return response.status == 200
    except OSError:
        return False


def buttons(widget):
    result = {}
    for child in widget.winfo_children():
        if child.winfo_class() == "Button":
            result[child.cget("text")] = child
        result.update(buttons(child))
    return result


class ControllerVerification:
    """Drive widgets on Tk's main thread, letting service actions run asynchronously."""

    def __init__(self):
        self.window = create_controller()
        self.controls = buttons(self.window)
        self.phase = "stop"
        self.deadline = time.monotonic() + 55
        self.urls = []
        self.error = None

    def tick(self):
        try:
            if time.monotonic() >= self.deadline:
                raise TimeoutError(f"Controller did not complete {self.phase}")
            if self.phase == "stop":
                self.controls["停止"].invoke()
                self.phase = "stopped"
            elif self.phase == "stopped" and not responsive():
                self.controls["启动"].invoke()
                self.phase = "started"
            elif self.phase == "started" and responsive():
                self.controls["状态"].invoke()
                self.controls["打开网页界面"].invoke()
                assert self.urls == ["http://127.0.0.1:8130"]
                self.window.after(1000, self.window.destroy)
                return
            self.window.after(200, self.tick)
        except Exception as exc:
            self.error = exc
            self.window.destroy()

    def run(self):
        previous = webbrowser.open
        webbrowser.open = self.urls.append
        try:
            self.window.after(200, self.tick)
            self.window.mainloop()
        finally:
            webbrowser.open = previous
        if self.error:
            raise self.error
        assert responsive(), "Closing the controller stopped the service"
        return {
            "stop_start_widgets": True,
            "browser_url": self.urls[0],
            "service_survives_window_close": True,
        }


if __name__ == "__main__":
    if sys.platform in {"darwin", "win32"}:
        # This script is executed with the installed Python outside site-packages.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        if sys.platform == "darwin":
            from scripts.verify_macos_menu import verify_menu

            result = verify_menu()
        else:
            from scripts.verify_windows_tray import verify_tray

            result = verify_tray()
        assert responsive(), "Quitting the menu stopped the service"
        result["service_survives_menu_quit"] = True
    else:
        result = ControllerVerification().run()
    print(json.dumps(result))
