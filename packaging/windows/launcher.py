"""Native Windows desktop launcher for the Vybelix local cockpit."""

from __future__ import annotations

import argparse
import ctypes
import io
import os
import sys
import threading
import tkinter as tk
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from tkinter import filedialog, messagebox

from vybelix.cli import main as cli_main
from vybelix.ui import make_handler
import vybelix.ui as ui_module


class DesktopWindowControls:
    """Small, local-only bridge for the custom frameless window buttons."""

    def __init__(self) -> None:
        self.window = None
        self.maximized = False

    def minimize(self) -> bool:
        if self.window is None:
            return False
        self.window.minimize()
        return True

    def toggle_maximize(self) -> bool:
        if self.window is None:
            return False
        if self.maximized:
            self.window.restore()
        else:
            self.window.maximize()
        self.maximized = not self.maximized
        return self.maximized

    def close(self) -> bool:
        if self.window is None:
            return False
        self.window.destroy()
        return True


def _set_rounded_corners(window) -> None:
    """Ask Windows 11 DWM to round this top-level window when supported."""
    if sys.platform != "win32":
        return
    try:
        handle = ctypes.c_void_p(int(window.native.Handle))
        preference = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.WinDLL("dwmapi").DwmSetWindowAttribute(
            handle, 33, ctypes.byref(preference), ctypes.sizeof(preference)
        )
    except Exception:
        # Windows versions without this DWM attribute still render the UI normally.
        pass


def _choose_project(parent: tk.Tk, initial: str | None) -> Path | None:
    selected = initial or filedialog.askdirectory(
        parent=parent,
        title="Choisir le dossier du projet à ouvrir dans Vybelix",
        mustexist=True,
    )
    return Path(selected).expanduser().resolve() if selected else None


def _ensure_project(parent: tk.Tk, project: Path) -> bool:
    if (project / "vybelix.toml").is_file() or (project / "codelix.toml").is_file():
        return True
    initialize = messagebox.askyesno(
        "Initialiser le projet",
        "Ce dossier n’a pas encore de configuration Vybelix.\n\n"
        "Créer la configuration locale et la progression dans ce dossier ?\n"
        "Aucune clé API ne sera créée ni copiée.",
        parent=parent,
    )
    if not initialize:
        return False
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = cli_main(["init", str(project)])
        if result != 0:
            raise RuntimeError("L’initialisation du dossier a échoué.")
        return True
    except Exception as exc:
        messagebox.showerror("Initialisation impossible", str(exc), parent=parent)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Lance l’application de bureau Vybelix.")
    parser.add_argument("--project", help="Ouvrir directement ce dossier projet.")
    args = parser.parse_args()

    root = tk.Tk()
    root.withdraw()
    project = _choose_project(root, args.project)
    if project is None:
        root.destroy()
        return 0
    if not project.is_dir():
        messagebox.showerror("Dossier introuvable", "Le dossier projet sélectionné n’existe pas.", parent=root)
        root.destroy()
        return 1
    if not _ensure_project(root, project):
        root.destroy()
        return 0
    root.destroy()

    try:
        import webview
    except Exception as exc:
        fallback = tk.Tk()
        fallback.withdraw()
        messagebox.showerror(
            "Composant de fenêtre indisponible",
            "Vybelix ne peut pas charger sa fenêtre de bureau. Réinstalle l’application.\n\n"
            f"Détail : {exc}",
            parent=fallback,
        )
        fallback.destroy()
        return 1

    try:
        static_root = Path(ui_module.__file__).with_name("ui_assets")
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(project, static_root))
    except Exception as exc:
        fallback = tk.Tk()
        fallback.withdraw()
        messagebox.showerror("Vybelix ne peut pas démarrer", str(exc), parent=fallback)
        fallback.destroy()
        return 1

    server_thread = threading.Thread(target=server.serve_forever, name="Vybelix-local-server", daemon=True)
    server_thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    storage_path = local_app_data / "Vybelix" / "WebView2"
    storage_path.mkdir(parents=True, exist_ok=True)
    controls = DesktopWindowControls()

    try:
        window = webview.create_window(
            "Vybelix",
            url=url,
            js_api=controls,
            width=1440,
            height=920,
            min_size=(1024, 680),
            background_color="#100b1d",
            text_select=True,
            frameless=True,
            easy_drag=False,
            shadow=True,
        )
        controls.window = window
        window.events.before_show += _set_rounded_corners
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(storage_path))
    except Exception as exc:
        fallback = tk.Tk()
        fallback.withdraw()
        messagebox.showerror(
            "Fenêtre Vybelix indisponible",
            "Le moteur WebView2 n’a pas pu ouvrir Vybelix. Vérifie que Microsoft Edge WebView2 Runtime est installé.\n\n"
            f"Détail : {exc}",
            parent=fallback,
        )
        fallback.destroy()
        return 1
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())