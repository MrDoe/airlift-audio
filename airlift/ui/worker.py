"""Background batch worker: one model load, sequential per-file jobs."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.apollo import ApolloRestorer, CancelledError
from ..core.pipeline import EnhanceOptions, enhance_file


class BatchWorker(QThread):
    model_status = Signal(str, float)
    item_progress = Signal(int, str, float)
    item_done = Signal(int, object)
    item_failed = Signal(int, str)
    fatal = Signal(str)
    finished_all = Signal()

    def __init__(
        self,
        jobs: list[Path],
        options: EnhanceOptions,
        device_preference: str = "auto",
        restorer: ApolloRestorer | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.jobs = jobs
        self.options = options
        self.device_preference = device_preference
        self.restorer = restorer
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        try:
            if self.restorer is None:
                self.model_status.emit("Preparing model", 0.0)
                self.restorer = ApolloRestorer(self.device_preference)
                self.restorer.load(
                    lambda stage, fraction: self.model_status.emit(stage, fraction)
                )
                self.model_status.emit("Model ready", 1.0)
        except Exception as exc:  # model problems are fatal for the batch
            self.fatal.emit(f"Could not load the model: {exc}")
            self.finished_all.emit()
            return

        for index, path in enumerate(self.jobs):
            if self._cancel.is_set():
                break
            try:
                result = enhance_file(
                    path,
                    self.options,
                    self.restorer,
                    progress=lambda stage, fraction, i=index: self.item_progress.emit(
                        i, stage, fraction
                    ),
                    cancel=self._cancel.is_set,
                )
                self.item_done.emit(index, result)
            except CancelledError:
                break
            except Exception as exc:  # keep the rest of the batch alive
                self.item_failed.emit(index, str(exc))

        self.finished_all.emit()
