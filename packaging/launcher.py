"""PyInstaller entry point (absolute imports so the frozen app can find the package)."""

from airlift.app import main

raise SystemExit(main())
