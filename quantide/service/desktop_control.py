"""Small foreground controller, independent of the web service's lifetime."""

import ctypes
import os
import subprocess
import sys
import threading
import webbrowser

from quantide.config.paths import get_app_config_dir


def _controller_buttons(window, action):
    """Build service actions and schedule controller status refreshes."""
    import tkinter as tk
    from tkinter import messagebox

    controls = tk.Frame(window)
    controls.pack(pady=8)
    for title, command in (("启动", "start"), ("停止", "stop"), ("状态", "status")):
        tk.Button(controls, text=title, command=lambda name=command: action(name)).pack(
            side="left", padx=5
        )
    from quantide.config.server_address import controller_url

    tk.Button(window, text="打开网页界面", command=lambda: webbrowser.open(controller_url())).pack(
        pady=5
    )
    tk.Button(
        window,
        text="日志位置",
        command=lambda: messagebox.showinfo(
            "日志",
            str(get_app_config_dir() / "logs")
            if os.name != "nt"
            else os.path.join(
                os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "MillionaireCE", "logs"
            ),
        ),
    ).pack()


def create_controller():
    """Build the native controls without transferring service process ownership."""
    import tkinter as tk

    window = tk.Tk()
    window.title("Millionaire CE")
    window.geometry("440x240")
    status = tk.StringVar(value="Millionaire CE 后台服务")
    action_lock = threading.Lock()
    tk.Label(window, textvariable=status, wraplength=410).pack(pady=18)

    def action(command):
        def work() -> None:
            with action_lock:
                try:
                    if sys.platform == "win32" and not ctypes.windll.shell32.IsUserAnAdmin():
                        arguments = f"-m quantide.cli service {command}"
                        result = ctypes.windll.shell32.ShellExecuteW(
                            None, "runas", sys.executable, arguments, None, 1
                        )
                        message = "已请求管理员操作" if result > 32 else "管理员操作未执行"
                    else:
                        result = subprocess.run(
                            [sys.executable, "-m", "quantide.cli", "service", command],
                            capture_output=True,
                            text=True,
                            timeout=40,
                        )
                        message = (result.stdout or result.stderr or f"exit={result.returncode}")[
                            -500:
                        ]
                    window.after(0, status.set, message)
                except Exception as exc:
                    window.after(0, status.set, str(exc))

        threading.Thread(target=work, daemon=True).start()

    _controller_buttons(window, action)
    return window


def main(*, install=False, uninstall=False, system=False):
    """Open service controls; closing this window leaves the background service running."""
    if sys.platform == "win32" and not (install or uninstall or system):
        from quantide.service.host_service import install_root

        tray = install_root() / "MillionaireTray.exe"
        if tray.exists():
            subprocess.Popen([str(tray)])
            return 0
    if sys.platform == "darwin":
        from quantide.service.macos_menu import (
            bundle_path,
            install_menu,
            open_menu,
            uninstall_menu,
        )

        if uninstall:
            return uninstall_menu(system)
        if install:
            return install_menu(system)
        if bundle_path().exists():
            return open_menu()
    if install or uninstall or system:
        raise ValueError("Menu registration requires a native macOS installation")
    create_controller().mainloop()
    return 0
