"""Demucs separation dialog: pick options, separate, collect the stems."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..core.stems import DEFAULT_MODEL, MODELS, StemOptions
from .icons import icon
from .worker import StemWorker

DEVICES = (("Auto", "auto"), ("CPU", "cpu"), ("CUDA", "cuda"), ("Apple MPS", "mps"))


class StemDialog(QDialog):
    """Separate a batch of files into vocals + instrumental (Demucs)."""

    stems_ready = Signal(list)

    def __init__(
        self,
        files: list[Path],
        *,
        device: str = "auto",
        output_dir: Path | None = None,
        demucs_python: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.files = list(files)
        self.outputs: list[Path] = []
        self.failures: list[str] = []
        self.worker: StemWorker | None = None

        self.setWindowTitle("Separate stems")
        self.setMinimumWidth(620)
        self.resize(640, 620)
        self._build(
            device=device,
            output_dir=output_dir,
            demucs_python=demucs_python,
        )

    # ------------------------------------------------------------------ UI
    def _build(
        self,
        *,
        device: str,
        output_dir: Path | None,
        demucs_python: str | None,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        headline = QLabel("Separate stems")
        headline.setProperty("role", "title")
        layout.addWidget(headline)

        description = QLabel(
            f"Split {len(self.files)} file(s) into vocals and instrumental with Demucs."
        )
        description.setProperty("role", "muted")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.NoSelection)
        self.file_list.setMaximumHeight(120)
        for path in self.files:
            self.file_list.addItem(str(path))
        layout.addWidget(self.file_list)

        box = QGroupBox("Options")
        form = QFormLayout(box)

        self.model_combo = QComboBox()
        for model in MODELS:
            self.model_combo.addItem(model, model)
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(DEFAULT_MODEL)))
        form.addRow("Model", self.model_combo)

        self.device_combo = QComboBox()
        for label, value in DEVICES:
            self.device_combo.addItem(label, value)
        self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(device)))
        form.addRow("Device", self.device_combo)

        self.format_combo = QComboBox()
        self.format_combo.addItem("WAV float", "wav")
        self.format_combo.addItem("FLAC 24-bit", "flac")
        form.addRow("Format", self.format_combo)

        out_row = QHBoxLayout()
        self.output_edit = QLineEdit(str(output_dir) if output_dir else "")
        self.output_edit.setPlaceholderText("next to each source file")
        self.out_btn = QPushButton("Browse…")
        self.out_btn.clicked.connect(self._pick_output)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(self.out_btn)
        form.addRow("Output folder", out_row)

        self.four_stems = QCheckBox("Also write drums, bass and other")
        form.addRow("", self.four_stems)

        py_row = QHBoxLayout()
        self.python_edit = QLineEdit(demucs_python or "")
        self.python_edit.setPlaceholderText("auto (AIRLIFT_DEMUCS_PYTHON or this Python)")
        self.python_edit.setToolTip(
            "Interpreter that can import demucs. Leave empty to auto-detect."
        )
        py_row.addWidget(self.python_edit, 1)
        self.py_btn = QPushButton("Browse…")
        self.py_btn.clicked.connect(self._pick_python)
        py_row.addWidget(self.py_btn)
        form.addRow("Demucs Python", py_row)
        layout.addWidget(box)

        self.add_to_queue = QCheckBox("Add the separated stems to the queue")
        self.add_to_queue.setChecked(True)
        layout.addWidget(self.add_to_queue)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

        self.status = QLabel("Ready.")
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.start_btn = QPushButton("Separate")
        self.start_btn.setProperty("variant", "primary")
        self.start_btn.setIcon(icon("layers", "#06201C"))
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("variant", "ghost")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

    def _pick_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder")
        if folder:
            self.output_edit.setText(folder)

    def _pick_python(self) -> None:
        start = str(Path(self.python_edit.text()).parent) if self.python_edit.text() else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a Python interpreter with Demucs", start, "All files (*)"
        )
        if path:
            self.python_edit.setText(path)

    # --------------------------------------------------------------- run
    def _options(self) -> StemOptions:
        out = self.output_edit.text().strip()
        return StemOptions(
            model=self.model_combo.currentData(),
            device=self.device_combo.currentData(),
            output_dir=Path(out).expanduser() if out else None,
            four_stems=self.four_stems.isChecked(),
            fmt=self.format_combo.currentData(),
            demucs_python=self.python_edit.text().strip() or None,
        )

    def _start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.outputs.clear()
        self.failures.clear()
        self.progress.setValue(0)
        self._set_running(True)

        self.worker = StemWorker(self.files, self._options(), self)
        self.worker.item_progress.connect(self._on_progress)
        self.worker.item_done.connect(self._on_done)
        self.worker.item_failed.connect(self._on_failed)
        self.worker.fatal.connect(self._on_fatal)
        self.worker.finished_all.connect(self._on_finished)
        self.status.setText("Starting Demucs…")
        self.worker.start()

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status.setText("Cancelling…")

    def _on_progress(self, index: int, stage: str, fraction: float) -> None:
        total = max(1, len(self.files))
        overall = (index + max(0.0, min(1.0, fraction))) / total
        self.progress.setValue(int(overall * 100))
        self.status.setText(f"{index + 1}/{total} · {stage}")

    def _on_done(self, _index: int, result) -> None:
        for path in result.outputs.values():
            self.outputs.append(Path(path))
        self.status.setText(
            f"{result.source.name}: {len(result.outputs)} stem(s) in "
            f"{result.elapsed:.1f}s on {result.device}."
        )

    def _on_failed(self, index: int, message: str) -> None:
        name = self.files[index].name if 0 <= index < len(self.files) else "file"
        self.failures.append(f"{name}: {message}")
        self.status.setText(f"{name}: failed.")

    def _on_fatal(self, message: str) -> None:
        QMessageBox.critical(self, APP_NAME, message)

    def _on_finished(self) -> None:
        self._set_running(False)
        cancelled = bool(self.worker and self.worker.cancelled)
        self.progress.setValue(100 if self.outputs else 0)

        if self.outputs and self.add_to_queue.isChecked():
            self.stems_ready.emit([str(path) for path in self.outputs])

        if cancelled:
            self.status.setText("Cancelled.")
            return
        if self.failures:
            shown = "\n".join(self.failures[:5])
            QMessageBox.warning(
                self,
                APP_NAME,
                f"{len(self.failures)} file(s) failed:\n\n{shown}",
            )
        elif self.outputs:
            folders = sorted({str(path.parent) for path in self.outputs})
            self.status.setText(f"Wrote {len(self.outputs)} stem(s).")
            QMessageBox.information(
                self,
                APP_NAME,
                f"Wrote {len(self.outputs)} stem(s) to:\n" + "\n".join(folders),
            )
        else:
            self.status.setText("Nothing to do.")

    def _set_running(self, running: bool) -> None:
        for widget in (
            self.file_list,
            self.model_combo,
            self.device_combo,
            self.format_combo,
            self.output_edit,
            self.out_btn,
            self.four_stems,
            self.python_edit,
            self.py_btn,
            self.add_to_queue,
        ):
            widget.setEnabled(not running)
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.close_btn.setEnabled(not running)

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        super().reject()
