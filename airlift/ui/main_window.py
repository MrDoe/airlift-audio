"""Main window: queue, settings, analysis, A/B listening."""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path

import soundfile as sf
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_ID, APP_NAME, ORG_NAME, __version__
from ..core.apollo import ApolloRestorer, describe_device
from ..core.audio import (
    BAND_EDGES,
    SAMPLE_RATE,
    band_labels,
    decode,
    make_ab_clip,
    measure_lufs,
)
from ..core.pipeline import (
    AUDIO_SUFFIXES,
    EnhanceOptions,
    EnhanceResult,
)
from .player import MULTIMEDIA, ABPlayer

COLUMNS = ["File", "Duration", "Status", "Progress"]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_ID)
        self.jobs: list[Path] = []
        self.results: dict[str, EnhanceResult] = {}
        self.worker = None
        self.restorer: ApolloRestorer | None = None
        self._active_rows: list[int] = []

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1060, 760)
        self.setMinimumSize(860, 620)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_ui()
        self._build_menu()
        self._load_settings()
        self._log(f"{APP_NAME} {__version__} ready.")

    # ------------------------------------------------------------------ UI
    def _build_actions(self) -> None:
        style = self.style()
        self.act_add = QAction(style.standardIcon(style.StandardPixmap.SP_DialogOpenButton),
                               "Add files", self)
        self.act_add.setShortcut(QKeySequence.Open)
        self.act_add.triggered.connect(self.add_files)

        self.act_folder = QAction(style.standardIcon(style.StandardPixmap.SP_DirOpenIcon),
                                  "Add folder", self)
        self.act_folder.setShortcut("Ctrl+Shift+O")
        self.act_folder.triggered.connect(self.add_folder)

        self.act_remove = QAction(style.standardIcon(style.StandardPixmap.SP_TrashIcon),
                                  "Remove", self)
        self.act_remove.setShortcut(QKeySequence.Delete)
        self.act_remove.triggered.connect(self.remove_selected)

        self.act_clear = QAction("Clear", self)
        self.act_clear.triggered.connect(self.clear_all)

        self.act_start = QAction(style.standardIcon(style.StandardPixmap.SP_MediaPlay),
                                 "Enhance", self)
        self.act_start.setShortcut("Ctrl+Return")
        self.act_start.triggered.connect(self.start_batch)
        self.act_start.setEnabled(False)

        self.act_cancel = QAction(style.standardIcon(style.StandardPixmap.SP_MediaStop),
                                  "Cancel", self)
        self.act_cancel.setEnabled(False)
        self.act_cancel.triggered.connect(self.cancel_batch)

        self.act_stems = QAction("Separate stems", self)
        self.act_stems.setShortcut("Ctrl+Shift+S")
        self.act_stems.setToolTip("Split into vocals and instrumental with Demucs")
        self.act_stems.setEnabled(False)
        self.act_stems.triggered.connect(self.open_stem_dialog)

    def _build_ui(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        for action in (self.act_add, self.act_folder, self.act_remove, self.act_clear):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.act_start)
        toolbar.addAction(self.act_cancel)
        toolbar.addSeparator()
        toolbar.addAction(self.act_stems)
        self.addToolBar(toolbar)

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        root.addWidget(self._build_settings())

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_queue())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([380, 300])
        root.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self.overall = QProgressBar()
        self.overall.setFixedWidth(200)
        self.overall.setRange(0, 100)
        self.overall.setVisible(False)
        self.status_label = QLabel("Idle")
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.overall)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.dock = QDockWidget("Activity log", self)
        self.dock.setObjectName("logdock")
        self.dock.setWidget(self.log_view)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
        self.dock.hide()

    def _build_settings(self) -> QGroupBox:
        box = QGroupBox("Restoration")
        outer = QVBoxLayout(box)
        outer.setSpacing(6)

        row = QHBoxLayout()
        row.addWidget(QLabel("Air"))
        self.shelf_spin = QDoubleSpinBox()
        self.shelf_spin.setRange(0.0, 6.0)
        self.shelf_spin.setSingleStep(0.5)
        self.shelf_spin.setDecimals(1)
        self.shelf_spin.setSuffix(" dB")
        self.shelf_spin.setValue(2.5)
        self.shelf_spin.setToolTip(
            "High-shelf boost compensating Apollo's treble tilt. 0 dB = raw output."
        )
        row.addWidget(self.shelf_spin)

        row.addWidget(QLabel("above"))
        self.shelf_freq = QSpinBox()
        self.shelf_freq.setRange(4_000, 16_000)
        self.shelf_freq.setSingleStep(500)
        self.shelf_freq.setSuffix(" Hz")
        self.shelf_freq.setValue(9_000)
        row.addWidget(self.shelf_freq)

        row.addSpacing(12)
        row.addWidget(QLabel("Format"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("WAV · 32-bit float", "wav")
        self.format_combo.addItem("FLAC · 24-bit", "flac")
        row.addWidget(self.format_combo)

        row.addSpacing(12)
        row.addWidget(QLabel("Output"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Same folder as source")
        self.output_edit.setClearButtonEnabled(True)
        row.addWidget(self.output_edit, 1)
        out_btn = QToolButton()
        out_btn.setText("…")
        out_btn.clicked.connect(self.pick_output_dir)
        row.addWidget(out_btn)

        row.addSpacing(12)
        row.addWidget(QLabel("Device"))
        self.device_combo = QComboBox()
        self.device_combo.addItem("Auto", "auto")
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("CUDA", "cuda")
        self.device_combo.addItem("Apple MPS", "mps")
        row.addWidget(self.device_combo)
        outer.addLayout(row)

        self.advanced_toggle = QCheckBox("Advanced")
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        outer.addWidget(self.advanced_toggle)

        adv = QWidget()
        adv_row = QHBoxLayout(adv)
        adv_row.setContentsMargins(0, 0, 0, 0)
        adv_row.addWidget(QLabel("Chunk"))
        self.chunk_spin = self._seconds_spin(6.0, 2.0, 30.0)
        adv_row.addWidget(self.chunk_spin)
        adv_row.addWidget(QLabel("Overlap"))
        self.overlap_spin = self._seconds_spin(1.0, 0.0, 5.0)
        adv_row.addWidget(self.overlap_spin)
        adv_row.addWidget(QLabel("Pad"))
        self.pad_spin = self._seconds_spin(1.0, 0.0, 5.0)
        adv_row.addWidget(self.pad_spin)
        adv_row.addWidget(QLabel("Batch"))
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 8)
        self.batch_spin.setValue(2)
        adv_row.addWidget(self.batch_spin)
        adv_row.addStretch(1)
        self.advanced_panel = adv
        self.advanced_panel.setVisible(False)
        outer.addWidget(self.advanced_panel)
        return box

    @staticmethod
    def _seconds_spin(value: float, low: float, high: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(0.5)
        spin.setDecimals(1)
        spin.setSuffix(" s")
        spin.setValue(value)
        return spin

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)

    def _build_queue(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        title = QLabel("Queue")
        title.setStyleSheet("font-weight: 600; color: #aab4c3;")
        header.addWidget(title)
        header.addStretch(1)
        self.queue_hint = QLabel("Drop audio files here, or use Add files")
        self.queue_hint.setStyleSheet("color: #6d7787;")
        header.addWidget(self.queue_hint)

        self.play_btn = QPushButton("Play")
        self.play_btn.setEnabled(False)
        self.play_btn.setToolTip("Preview the selected file")
        self.play_btn.clicked.connect(self.play_selected)
        header.addWidget(self.play_btn)

        self.separate_btn = QPushButton("Separate stems")
        self.separate_btn.setEnabled(False)
        self.separate_btn.setToolTip("Split the selected file (or the whole queue) into stems")
        self.separate_btn.clicked.connect(self.open_stem_dialog)
        header.addWidget(self.separate_btn)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self.table, 1)
        return wrap

    def _build_detail(self) -> QWidget:
        box = QGroupBox("Comparison")
        layout = QVBoxLayout(box)

        self.detail_title = QLabel("Select a finished file to inspect it.")
        self.detail_title.setStyleSheet("color: #9aa6b6;")
        self.detail_title.setWordWrap(True)
        layout.addWidget(self.detail_title)

        self.band_table = QTableWidget(len(BAND_EDGES) - 1, 4)
        self.band_table.setHorizontalHeaderLabels(["Band", "Original", "Enhanced", "Δ"])
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.band_table.setSelectionMode(QTableWidget.NoSelection)
        self.band_table.setAlternatingRowColors(True)
        self.band_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.band_table.setMaximumHeight(210)
        labels = band_labels()
        for row, label in enumerate(labels):
            item = QTableWidgetItem(label)
            item.setForeground(QColor("#8b95a5"))
            self.band_table.setItem(row, 0, item)
        layout.addWidget(self.band_table)

        self.player = ABPlayer()
        layout.addWidget(self.player)

        buttons = QHBoxLayout()
        self.export_ab_btn = QPushButton("Export 40 s A/B clip")
        self.export_ab_btn.setEnabled(False)
        self.export_ab_btn.clicked.connect(self.export_ab)
        self.reveal_btn = QPushButton("Open output folder")
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self.reveal_output)
        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_report)
        buttons.addWidget(self.export_ab_btn)
        buttons.addWidget(self.reveal_btn)
        buttons.addWidget(self.copy_btn)
        buttons.addStretch(1)
        self.device_label = QLabel("")
        self.device_label.setStyleSheet("color: #6d7787;")
        buttons.addWidget(self.device_label)
        layout.addLayout(buttons)
        return box

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.act_add)
        file_menu.addAction(self.act_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.act_remove)
        file_menu.addAction(self.act_clear)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&View")
        toggle_log = self.dock.toggleViewAction()
        toggle_log.setText("Activity log")
        view_menu.addAction(toggle_log)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.act_stems)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About Airlift Audio", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    # -------------------------------------------------------------- settings
    def _load_settings(self) -> None:
        s = self.settings
        self.shelf_spin.setValue(float(s.value("shelf_db", 2.5)))
        self.shelf_freq.setValue(int(s.value("shelf_freq", 9000)))
        index = self.format_combo.findData(s.value("format", "wav"))
        self.format_combo.setCurrentIndex(max(0, index))
        self.output_edit.setText(str(s.value("output_dir", "")))
        index = self.device_combo.findData(s.value("device", "auto"))
        self.device_combo.setCurrentIndex(max(0, index))
        self.demucs_python = str(
            s.value("demucs_python", os.environ.get("AIRLIFT_DEMUCS_PYTHON", ""))
        )
        self.chunk_spin.setValue(float(s.value("chunk_seconds", 6.0)))
        self.overlap_spin.setValue(float(s.value("overlap_seconds", 1.0)))
        self.pad_spin.setValue(float(s.value("pad_seconds", 1.0)))
        self.batch_spin.setValue(int(s.value("batch_size", 2)))
        geometry = s.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("shelf_db", self.shelf_spin.value())
        s.setValue("shelf_freq", self.shelf_freq.value())
        s.setValue("format", self.format_combo.currentData())
        s.setValue("output_dir", self.output_edit.text())
        s.setValue("device", self.device_combo.currentData())
        s.setValue("demucs_python", self.demucs_python)
        s.setValue("chunk_seconds", self.chunk_spin.value())
        s.setValue("overlap_seconds", self.overlap_spin.value())
        s.setValue("pad_seconds", self.pad_spin.value())
        s.setValue("batch_size", self.batch_spin.value())
        s.setValue("geometry", self.saveGeometry())

    # ------------------------------------------------------------------ jobs
    def add_files(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(AUDIO_SUFFIXES))
        files, _ = QFileDialog.getOpenFileNames(
            self, "Add audio files", "", f"Audio files ({patterns});;All files (*)"
        )
        if files:
            self._add_paths([Path(f) for f in files])

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add folder")
        if folder:
            self._add_paths([Path(folder)])

    def _add_paths(self, paths: list[Path]) -> None:
        found: list[Path] = []
        for path in paths:
            path = path.expanduser()
            if path.is_dir():
                for root, _dirs, files in os.walk(path):
                    for name in sorted(files):
                        candidate = Path(root) / name
                        if candidate.suffix.lower() in AUDIO_SUFFIXES:
                            found.append(candidate)
            elif path.suffix.lower() in AUDIO_SUFFIXES:
                found.append(path)
        existing = {str(p.resolve()) for p in self.jobs}
        added = 0
        for path in found:
            key = str(path.resolve())
            if key in existing:
                continue
            existing.add(key)
            self._append_row(path)
            added += 1
        if added:
            self.queue_hint.setVisible(False)
            self.act_start.setEnabled(True)
            self.act_stems.setEnabled(True)
            self.separate_btn.setEnabled(True)
            self._log(f"Added {added} file(s).")
            if self.table.currentRow() < 0 and self.table.rowCount() > 0:
                self.table.selectRow(0)
        elif paths:
            self._log("No new audio files found (unsupported or duplicate).")

    def open_stem_dialog(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.jobs):
            files = [self.jobs[row]]
        else:
            files = list(self.jobs)
        if not files:
            QMessageBox.information(
                self, APP_NAME, "Add audio files to the queue first."
            )
            return

        from .stem_dialog import StemDialog

        out = self.output_edit.text().strip()
        dialog = StemDialog(
            files,
            device=self.device_combo.currentData(),
            output_dir=Path(out).expanduser() if out else None,
            demucs_python=self.demucs_python or None,
            parent=self,
        )
        dialog.stems_ready.connect(self._add_stems)
        dialog.exec()
        self.demucs_python = dialog.python_edit.text().strip()

    def _add_stems(self, paths: list[str]) -> None:
        self._add_paths([Path(path) for path in paths])
        self._log(f"Added {len(paths)} separated stem(s) to the queue.")

    def play_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.jobs)):
            return
        path = self.jobs[row]
        result = self.results.get(str(path))
        if result is not None:
            self._show_detail(row)
        else:
            self.player.set_sources(path, None)
        if MULTIMEDIA and self.player.player is not None:
            self.player.player.play()

    def _append_row(self, path: Path) -> None:
        row = self.table.rowCount()
        self.jobs.append(path)
        self.table.insertRow(row)
        name = QTableWidgetItem(path.name)
        name.setToolTip(str(path))
        self.table.setItem(row, 0, name)

        duration = "–"
        try:
            info = sf.info(str(path))
            seconds = info.frames / info.samplerate if info.samplerate else 0
            duration = f"{int(seconds // 60)}:{int(seconds % 60):02d}"
        except Exception:  # noqa: BLE001, S110
            pass
        dur_item = QTableWidgetItem(duration)
        dur_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 1, dur_item)

        self.table.setItem(row, 2, QTableWidgetItem("Pending"))
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(14)
        self.table.setCellWidget(row, 3, bar)

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.results.pop(str(self.jobs[row]), None)
            self.jobs.pop(row)
            self.table.removeRow(row)
        if not self.jobs:
            self.queue_hint.setVisible(True)
            self.act_start.setEnabled(False)
            self.act_stems.setEnabled(False)
            self.separate_btn.setEnabled(False)
            self.play_btn.setEnabled(False)
        self._clear_detail()

    def clear_all(self) -> None:
        self.jobs.clear()
        self.results.clear()
        self.table.setRowCount(0)
        self.queue_hint.setVisible(True)
        self.act_start.setEnabled(False)
        self.act_stems.setEnabled(False)
        self.separate_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self._clear_detail()

    def _row_progress(self, row: int) -> QProgressBar | None:
        widget = self.table.cellWidget(row, 3)
        return widget if isinstance(widget, QProgressBar) else None

    def _set_status(self, row: int, text: str, tooltip: str = "",
                   color: str | None = None) -> None:
        item = self.table.item(row, 2)
        if item is None:
            item = QTableWidgetItem(text)
            self.table.setItem(row, 2, item)
        item.setText(text)
        item.setToolTip(tooltip)
        if color:
            item.setForeground(QColor(color))

    # ---------------------------------------------------------------- batch
    def _options(self) -> EnhanceOptions:
        out = self.output_edit.text().strip()
        return EnhanceOptions(
            shelf_db=self.shelf_spin.value(),
            shelf_freq=float(self.shelf_freq.value()),
            fmt=self.format_combo.currentData(),
            output_dir=Path(out).expanduser() if out else None,
            chunk_seconds=self.chunk_spin.value(),
            overlap_seconds=self.overlap_spin.value(),
            pad_seconds=self.pad_spin.value(),
            batch_size=self.batch_spin.value(),
        )

    def start_batch(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        pending = [i for i, path in enumerate(self.jobs)
                   if str(path) not in self.results]
        if not pending:
            QMessageBox.information(self, APP_NAME, "Everything in the queue is already done.")
            return

        self._active_rows = pending
        self._pending_paths = [self.jobs[i] for i in pending]
        for row in pending:
            self._set_status(row, "Queued")
            bar = self._row_progress(row)
            if bar:
                bar.setValue(0)

        options = self._options()
        device = self.device_combo.currentData()

        from .worker import BatchWorker

        self.worker = BatchWorker(self._pending_paths, options, device, self.restorer)
        self.worker.model_status.connect(self._on_model_status)
        self.worker.item_progress.connect(self._on_item_progress)
        self.worker.item_done.connect(self._on_item_done)
        self.worker.item_failed.connect(self._on_item_failed)
        self.worker.fatal.connect(self._on_fatal)
        self.worker.finished_all.connect(self._on_batch_finished)

        self._set_running(True)
        self.overall.setVisible(True)
        self.overall.setValue(0)
        self.status_label.setText("Loading model…")
        self._log(f"Starting batch: {len(pending)} file(s), device {device}.")
        self.worker.start()

    def cancel_batch(self) -> None:
        if self.worker and self.worker.isRunning():
            self._log("Cancelling after the current chunk…")
            self.worker.cancel()
            self.act_cancel.setEnabled(False)
            self.status_label.setText("Cancelling…")

    def _set_running(self, running: bool) -> None:
        for action in (self.act_add, self.act_folder, self.act_remove,
                       self.act_clear, self.act_start, self.act_stems):
            action.setEnabled(not running)
        self.act_cancel.setEnabled(running)
        if not running:
            self.act_start.setEnabled(bool(self.jobs))
            self.act_stems.setEnabled(bool(self.jobs))
            self.separate_btn.setEnabled(bool(self.jobs))
            self.play_btn.setEnabled(
                (not running) and self.table.currentRow() >= 0 and MULTIMEDIA
            )
        else:
            self.play_btn.setEnabled(False)
            self.separate_btn.setEnabled(False)

    def _on_model_status(self, stage: str, fraction: float) -> None:
        self.status_label.setText(stage)
        self.overall.setValue(int(max(0.0, min(1.0, fraction)) * 100))
        if stage.lower().startswith(("downloading", "loading")):
            self._log(stage)

    def _row_for_index(self, index: int) -> int | None:
        if 0 <= index < len(self._active_rows):
            return self._active_rows[index]
        return None

    def _on_item_progress(self, index: int, stage: str, fraction: float) -> None:
        row = self._row_for_index(index)
        if row is None:
            return
        bar = self._row_progress(row)
        if bar:
            bar.setValue(int(max(0.0, min(1.0, fraction)) * 100))
        self._set_status(row, stage, f"{fraction*100:.0f}%")
        done = sum(1 for r in self._active_rows
                   if self.table.item(r, 2) and self.table.item(r, 2).text() == "Done")
        self.status_label.setText(f"File {done + 1} of {len(self._active_rows)} · {stage}")

    def _on_item_done(self, index: int, result: EnhanceResult) -> None:
        row = self._row_for_index(index)
        if row is None:
            return
        path = result.source
        self.results[str(path)] = result
        bar = self._row_progress(row)
        if bar:
            bar.setValue(100)
        self._set_status(row, "Done", str(result.output), "#63d2c3")
        self._log(
            f"Done: {path.name} → {result.output.name} "
            f"({result.elapsed:.1f}s, peak {result.peak:.1f} dBFS)"
        )
        if self.table.currentRow() == row:
            self._show_detail(row)

    def _on_item_failed(self, index: int, message: str) -> None:
        row = self._row_for_index(index)
        if row is None:
            return
        self._set_status(row, "Failed", message, "#e06c75")
        self._log(f"Failed: {self.jobs[row].name}: {message}")
        bar = self._row_progress(row)
        if bar:
            bar.setValue(0)

    def _on_fatal(self, message: str) -> None:
        self._log(message)
        QMessageBox.critical(self, APP_NAME, message)

    def _on_batch_finished(self) -> None:
        if self.worker and self.worker.restorer is not None:
            self.restorer = self.worker.restorer
        cancelled = bool(self.worker and self.worker.cancelled)
        if cancelled:
            for row in self._active_rows:
                item = self.table.item(row, 2)
                if item and item.text() not in {"Done", "Failed"}:
                    self._set_status(row, "Cancelled", color="#d7a65f")
        self._set_running(False)
        self.overall.setVisible(False)
        if self.restorer:
            try:
                self.device_label.setText(describe_device(self.restorer.device))
            except Exception:  # noqa: BLE001
                self.device_label.setText(self.restorer.device)
        self.status_label.setText("Cancelled" if cancelled else "Idle")
        self._log("Batch cancelled." if cancelled else "Batch finished.")
        # Release the worker only after the signal emission completes; dropping
        # the last reference inside the slot can abort delivery to later slots.
        worker = self.worker
        QTimer.singleShot(0, lambda: self._release_worker(worker))

    def _release_worker(self, worker) -> None:
        if self.worker is worker:
            self.worker = None

    # --------------------------------------------------------------- detail
    def _on_selection(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self._show_detail(row)

        self.play_btn.setEnabled(row >= 0 and MULTIMEDIA)

    def _clear_detail(self) -> None:
        self.detail_title.setText("Select a finished file to inspect it.")
        for row in range(self.band_table.rowCount()):
            for column in range(1, 4):
                self.band_table.setItem(row, column, QTableWidgetItem(""))
        self.player.set_sources(None, None)
        self.export_ab_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)
        self.copy_btn.setEnabled(False)

    def _show_detail(self, row: int) -> None:
        if row < 0 or row >= len(self.jobs):
            return
        path = self.jobs[row]
        result = self.results.get(str(path))
        if result is None:
            self.detail_title.setText(f"{path.name} — not enhanced yet")
            self._clear_detail()
            self.detail_title.setText(f"{path.name} — not enhanced yet")
            return

        self.detail_title.setText(
            f"{result.source.name}  →  {result.output.name}   "
            f"·  {result.elapsed:.1f}s  ·  peak {result.peak:.1f} dBFS"
        )
        bands = band_labels()
        for i, label in enumerate(bands):
            original = result.before.get(label)
            enhanced = result.after.get(label)
            self.band_table.setItem(i, 1, self._num(original))
            self.band_table.setItem(i, 2, self._num(enhanced))
            if original is None or enhanced is None:
                self.band_table.setItem(i, 3, QTableWidgetItem("–"))
            else:
                delta = enhanced - original
                item = self._num(delta, signed=True)
                item.setForeground(QColor("#63d2c3" if delta >= 0 else "#d7a65f"))
                self.band_table.setItem(i, 3, item)

        self.player.set_sources(result.source, result.output)
        self.export_ab_btn.setEnabled(True)
        self.reveal_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        try:
            self.device_label.setText(describe_device(result.device))
        except Exception:  # noqa: BLE001
            self.device_label.setText(result.device)

    @staticmethod
    def _num(value: float | None, signed: bool = False) -> QTableWidgetItem:
        text = "–" if value is None else (f"{value:+.1f}" if signed else f"{value:.1f}")
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def reveal_output(self) -> None:
        row = self.table.currentRow()
        result = self.results.get(str(self.jobs[row])) if row >= 0 else None
        if result and result.output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.output.parent)))

    def copy_report(self) -> None:
        row = self.table.currentRow()
        result = self.results.get(str(self.jobs[row])) if row >= 0 else None
        if not result:
            return
        lines = [
            f"{result.source.name} -> {result.output.name}",
            (
                f"device: {result.device}  duration: {result.duration:.1f}s  "
                f"elapsed: {result.elapsed:.1f}s"
            ),
            f"peak: {result.peak:.1f} dBFS  rms: {result.rms:.1f} dBFS",
            "",
            f"{'band':>10} {'original':>10} {'enhanced':>10} {'delta':>8}",
        ]
        for label in band_labels():
            before = result.before.get(label)
            after = result.after.get(label)
            if before is None or after is None:
                continue
            lines.append(f"{label:>10} {before:10.1f} {after:10.1f} {after-before:+8.1f}")
        QApplication.clipboard().setText("\n".join(lines))
        self._log("Report copied to clipboard.")

    def export_ab(self) -> None:
        row = self.table.currentRow()
        result = self.results.get(str(self.jobs[row])) if row >= 0 else None
        if not result:
            return
        default = result.output.with_name(result.output.stem + ".AB.wav")
        target, _ = QFileDialog.getSaveFileName(
            self, "Export A/B clip", str(default), "WAV (*.wav)"
        )
        if not target:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            start = 0.0
            if self.player.player is not None:
                start = self.player.player.position() / 1000.0
            original, _ = decode(result.source)
            enhanced, _ = decode(result.output)
            lufs_original = measure_lufs(result.source)
            lufs_enhanced = measure_lufs(result.output)
            if lufs_original is not None and lufs_enhanced is not None:
                enhanced = enhanced * (10 ** ((lufs_original - lufs_enhanced) / 20.0))
            clip = make_ab_clip(
                original, enhanced, start_seconds=start, seconds=40.0,
                block_seconds=8.0, repeats=1,
            )
            sf.write(target, clip, SAMPLE_RATE, subtype="PCM_24")
        except Exception:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, APP_NAME,
                                 "Could not export the A/B clip:\n\n" + traceback.format_exc())
            return
        QApplication.restoreOverrideCursor()
        self._log(f"A/B clip written: {target}")
        QMessageBox.information(self, APP_NAME, f"A/B clip written:\n{target}")

    def pick_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder")
        if folder:
            self.output_edit.setText(folder)

    # ------------------------------------------------------------ misc/logs
    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")
        self.statusBar().showMessage(message, 4000)

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Local restoration for lossy and codec-damaged music.</p>"
            "<p>Restoration: <b>Apollo</b> (Kai Li &amp; Yi Luo, Tsinghua / Tencent AI Lab), "
            "CC BY-SA 4.0. Model code is bundled unmodified in "
            "<code>third_party/apollo</code>.</p>"
            "<p>This application is MIT licensed. Qt/PySide6 is LGPLv3. "
            "FFmpeg is invoked as an external program.</p>",
        )

    # ------------------------------------------------------------- events
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()
                 if url.isLocalFile()]
        if paths:
            self._add_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(10_000)
        self._save_settings()
        super().closeEvent(event)
