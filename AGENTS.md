# AGENTS.md

Airlift Audio: a PySide6 desktop app plus headless CLI for local Apollo audio
restoration. Python >= 3.10, setuptools, no lockfile. GUI and CLI share
`airlift/core/`.

## Setup

- `python -m venv .venv && . .venv/bin/activate`
- Install the CPU torch wheel **before** the project. `pip install -e .` only
  asks for `torch>=2.0`, so it can pull a CUDA wheel from PyPI and break the
  CPU PyInstaller build:
  `pip install "torch==2.8.0" --index-url https://download.pytorch.org/whl/cpu`
- `pip install -e .[dev]`
- Optional stem separation: `pip install -e .[stems]` (Demucs needs a matching
  `torchaudio`), or point `AIRLIFT_DEMUCS_PYTHON` at another interpreter that
  can import Demucs. Demucs is never bundled.

## Verify

- `pytest -q` (`addopts = "-q"` is already in `pyproject.toml`).
- One test: `pytest tests/test_cli.py::test_enhance_defaults`.
- Fast loop: exclude `tests/test_integration.py`. It runs real Apollo inference
  and downloads the ~66 MB weights on first use. `test_frozen_binary_cli`
  silently no-ops unless `dist/Airlift Audio/Airlift Audio` has been built.
- Lint like CI: `ruff check airlift tests --exclude airlift/third_party --exclude airlift/third_party/apollo`.
  Ruff is unpinned and newer releases already flag pre-existing default-rule
  findings; don't mass-fix unrelated files.
- Smoke: `airlift-audio --version`, `airlift-cli devices`. A bare
  `airlift-audio` launches the Qt GUI — avoid it in headless sessions.
- CI test job: Python 3.12 on Ubuntu, torch 2.8.0 CPU, then install, lint,
  `pytest -q`, and the two smoke commands. `ci.yml` triggers on `main` and pull
  requests, but the default branch is `master` — a direct push to `master` runs
  no checks, so open a PR when you want CI. Releases come from `v*` tags only.
- `docs/*.png` are rendered, not captured: `python scripts/make_screenshots.py`
  drives `MainWindow` on Qt's offscreen platform with synthetic queue data.
  Point `XDG_CONFIG_HOME` at a temp dir before creating a `MainWindow` in any
  headless script, or it writes to the real QSettings file.

## Architecture

- `airlift/core/` is UI-free; `airlift/cli.py` must not import Qt. Qt-only code
  belongs in `airlift/ui/`.
- `airlift.core.pipeline.enhance_file()` is the single enhancement path used by
  both the CLI and the GUI `BatchWorker`; change it once, not per frontend.
- Playback goes through the single `ABPlayer` mounted under the detail stack,
  so the transport is live for pending rows too. There is deliberately no Play
  button in the queue header — Space, the row context menu and **Queue → Play**
  all route to that one player.
- Audio is normalized to 44.1 kHz stereo float32 on decode. Output naming is
  `.enhanced.air.wav` when `shelf_db != 0`, `.enhanced.wav` when the shelf is
  off; FLAC switches the extension (`EnhanceOptions`; tests assert this).
- `airlift/core/apollo.py` prepends `airlift/third_party/apollo` to `sys.path`
  so the vendored `look2hear` imports as a top-level package. That third-party
  tree is unmodified CC BY-SA code: don't edit, reformat, or lint it.
- Apollo weights are fetched on first load from Hugging Face `JusperLee/Apollo`
  (`hf_hub_download`) and then reused in memory. Pass `checkpoint=` /
  `--checkpoint` for a local file.
- Stem separation shells out to `python -m demucs` in a subprocess (crash/cancel
  isolation). Interpreter resolution: explicit path → `AIRLIFT_DEMUCS_PYTHON` →
  current interpreter, but never `sys.executable` in a frozen bundle.
  `torchaudio` is deliberately not bundled.

## Packaging

- `packaging/launcher.py` is the frozen entrypoint. PyInstaller cannot see
  Qt-driven imports, so new `airlift.*` modules must be added to
  `hiddenimports` in **both** `packaging/airlift.spec` and
  `packaging/airlift-cuda.spec`.
- CPU builds refuse a CUDA-capable torch (`packaging/airlift.spec` and
  `packaging/check_release.py`); CUDA builds require it (`--allow-cuda` and
  `packaging/airlift-cuda.spec`). Run the gate before a one-folder build:
  `python packaging/check_release.py`.
- Build one-folder: `python -m PyInstaller packaging/airlift.spec --noconfirm`.
  Per-OS wrappers: `packaging/linux/build_appimage.sh`,
  `packaging/macos/build_dmg.sh`, `packaging/windows/build.ps1`. Linux CUDA
  variant: `PYTHON=... VARIANT=cuda bash packaging/linux/build_appimage.sh`.
- `build/`, `build-cuda/`, and `dist/` are gitignored PyInstaller output and can
  be huge; don't search or read them.
- Version is duplicated: `pyproject.toml`, `airlift/__init__.py`, the hardcoded
  greps in `.github/workflows/ci.yml`, both PyInstaller specs'
  `CFBundleShortVersionString`, `packaging/windows/airlift.iss`, the Linux/macOS
  script defaults, and a README example. Grep for the old version before
  bumping; releases are built from `v*` tags with `VERSION` from the tag.

## Conventions

- Python 3.10+ syntax: `from __future__ import annotations`, `X | None` types,
  stdlib `dataclasses`.
- Broad `except Exception` in batch loops is intentional (per-file failures must
  not abort the batch); keep the `# noqa: BLE001` reasons.
- Tests are plain pytest functions using `tmp_path`/`monkeypatch`; no custom
  fixtures or display are needed. Only the integration test needs network access
  (or a pre-populated Hugging Face cache).

<!-- BEGIN opencode-rag -->
## Code Navigation

ALWAYS use OpenCodeRAG tools before reading or editing:
- **Search first** — `search_semantic(query)` instead of grep/glob
- **Skeleton before read** — `get_file_skeleton(filePath)` then read specific lines
- **Usages before edit** — `find_usages(symbolName)` before modifying any symbol
- **Images via describe** — `describe_image(filePath, systemPrompt?)` — never read raw bytes
- **Recall quirks** — `recall_quirks(query)` when you hit a known pitfall
- **Add quirks** — `add_quirk(content)` when you discover a non-obvious fact
- **Fix quirks** — `update_quirk(id, ...)` / `delete_quirk(id)` when a stored quirk is outdated or wrong

If no results, run `opencode-rag index`.

### Decision tree — ALWAYS follow this order
1. User mentions code behavior/architecture → `search_semantic(query)`
2. User mentions a file path → `get_file_skeleton(filePath)` THEN `read` on specific lines
3. User mentions a function/class/variable to edit → `find_usages(symbolName)` THEN `search_semantic` THEN `edit`
4. User asks a code question → `search_semantic` to gather context before answering
5. User asks about an image or visual asset → `describe_image(filePath)` (optionally pass `systemPrompt` to focus on specific features) to retrieve its generated description, then optionally `search_semantic` for related code
6. You encounter an error or need to recall a known pitfall → `recall_quirks(query)`
7. You discover a non-obvious fact or workaround → `add_quirk(content)` to persist it for future sessions
8. A recalled quirk is outdated or wrong → `update_quirk(id, ...)` to fix it, or `delete_quirk(id)` if it no longer applies

### Proactive triggers — you MUST call these tools when
- User asks about code behavior, architecture, or implementation details
- User asks to edit, refactor, or fix code — call `find_usages` first
- User references files or functions you haven't read yet
- User says "find", "search", "look up", "where is", "how does"
- User refers to an image, screenshot, diagram, or visual asset
- Before answering ANY code-related question, retrieve context first
- Before reading ANY file, call `get_file_skeleton` to orient first

### Anti-patterns — NEVER do these
- Reading full files without calling `get_file_skeleton` first (wastes tokens)
- Editing a function without calling `find_usages` first (breaks call sites)
- Answering code questions without calling `search_semantic` first (you guess at behavior)
- Using `grep`/`glob` when `search_semantic` would find the answer faster
- Treating image files as text — use `describe_image` instead of reading raw bytes
- Using `npx opencode-rag quirk` shell commands instead of the built-in quirk tools (`add_quirk` / `recall_quirks` / `update_quirk` / `delete_quirk`) (the tools are faster, already loaded in-process, and go through the trust monitor)

### MANDATORY quirk capture rules — you MUST call `add_quirk` when
- A build, test, or type-check command fails and you resolve it
- You discover an undocumented library constraint, peer dep, or workaround
- You learn an environment-specific requirement (OS, tool version, etc.)
- You make a design decision that future sessions should remember
- You resolve a gotcha that cost more than one attempt

### MANDATORY quirk hygiene — you MUST call `update_quirk` or `delete_quirk` when
- A stored quirk is outdated, wrong, or has been fixed — update it or delete it instead of adding a contradicting duplicate
- NEVER finish a coding session without adding quirks for resolved errors.

### Long-running commands
Long-running commands:
- Any `shell` call expected to take more than 30s MUST set `background: true` (returns immediately; the session is notified on completion) or set an explicit `timeout` (ms).
- Default foreground timeout: 120000ms. Never run builds/tests/indexes in the foreground beyond 30s; if a call is already running, press Ctrl+B to background it (OpenCode: `session.background`).
- OpenCodeRAG measures foreground shell duration and records a quirk when a call exceeds the threshold, so repeated foreground runs become visible.
<!-- END opencode-rag -->
