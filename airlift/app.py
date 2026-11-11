"""Entry point: GUI by default, CLI subcommands when arguments are present."""

from __future__ import annotations

import sys
from pathlib import Path

from . import APP_ID, APP_NAME, ORG_NAME, __version__

USAGE = f"""{APP_NAME} {__version__}

Usage:
  airlift-audio                      launch the GUI
  airlift-audio enhance FILE...      restore from the command line
  airlift-audio compare A B          render an A/B clip
  airlift-audio separate FILE...     split into vocals + instrumental (Demucs)
  airlift-audio devices              show CUDA / MPS availability
  airlift-audio --version

Run `airlift-audio enhance --help` for the full option list.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in {"enhance", "compare", "separate", "devices"}:
        from .cli import main as cli_main

        return cli_main(args)
    if args and args[0] in {"--version", "-V"}:
        print(f"{APP_NAME} {__version__}")
        return 0
    if args and args[0] in {"--help", "-h"}:
        print(USAGE)
        return 0
    return run_gui()


def run_gui() -> int:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)

    icon_path = Path(__file__).resolve().parent / "assets" / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))

    apply_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
