"""A/B listening widget: same position, instant original/enhanced swap."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

try:  # QtMultimedia ships with PySide6; tolerate stripped builds.
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    MULTIMEDIA = True
except Exception:  # pragma: no cover - platform dependent
    MULTIMEDIA = False


def _clock(ms: int) -> str:
    seconds = max(0, ms // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


class ABPlayer(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current = "A"
        self._urls: dict[str, QUrl] = {}
        self._pending_ms = 0
        self._was_playing = False

        self.badge = QLabel("A · Original")
        self.badge.setStyleSheet(
            "font-weight: 700; color: #63d2c3; letter-spacing: 0.5px;"
        )
        self.badge.setMinimumWidth(110)

        self.play_button = QPushButton("Play")
        self.play_button.setEnabled(False)
        self.swap_button = QPushButton("Switch to B")
        self.swap_button.setEnabled(False)
        self.swap_button.setToolTip("Swap original/enhanced at the same position (B)")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setStyleSheet("color: #8b95a5;")

        self.status = QLabel("")
        self.status.setStyleSheet("color: #8b95a5;")

        controls = QHBoxLayout()
        controls.addWidget(self.badge)
        controls.addWidget(self.play_button)
        controls.addWidget(self.swap_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.time_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.status)

        if MULTIMEDIA:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.9)
            self.player.setAudioOutput(self.audio)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_duration)
            self.player.playbackStateChanged.connect(self._on_state)
            self.player.mediaStatusChanged.connect(self._on_media_status)
            self.player.errorOccurred.connect(self._on_error)
            self.play_button.clicked.connect(self._toggle_play)
            self.swap_button.clicked.connect(self.toggle)
            self.slider.sliderMoved.connect(self.player.setPosition)
            QShortcut(Qt.Key_Space, self, self._toggle_play)
            QShortcut(Qt.Key_B, self, self.toggle)
        else:
            self.player = None
            self.play_button.setVisible(False)
            self.swap_button.setVisible(False)
            self.slider.setVisible(False)
            self.status.setText("Audio preview unavailable (QtMultimedia missing).")

    # -- public API ------------------------------------------------------
    def set_sources(self, original: Path | None, enhanced: Path | None) -> None:
        self._urls.clear()
        if original and Path(original).is_file():
            self._urls["A"] = QUrl.fromLocalFile(str(Path(original)))
        if enhanced and Path(enhanced).is_file():
            self._urls["B"] = QUrl.fromLocalFile(str(Path(enhanced)))
        available = bool(self._urls)
        self.play_button.setEnabled(available and MULTIMEDIA)
        self.swap_button.setEnabled("A" in self._urls and "B" in self._urls)
        self.slider.setEnabled(available and MULTIMEDIA)
        if not available:
            self.badge.setText("A · Original")
            self.status.setText("")
            return
        self.current = "A" if "A" in self._urls else "B"
        self._update_badge()
        self._load_current(0, autoplay=False)
        if self._urls.get("A") is None:
            self.status.setText("Only the enhanced file is available.")
        else:
            self.status.setText("Space: play/pause · B: switch A/B")

    def toggle(self) -> None:
        if "A" not in self._urls or "B" not in self._urls:
            return
        position = self.player.position() if self.player else 0
        self._was_playing = bool(
            self.player and self.player.playbackState() == QMediaPlayer.PlayingState
        )
        self.current = "B" if self.current == "A" else "A"
        self._update_badge()
        self._load_current(position, autoplay=self._was_playing)

    # -- internals -------------------------------------------------------
    def _update_badge(self) -> None:
        self.badge.setText("A · Original" if self.current == "A" else "B · Enhanced")
        self.swap_button.setText(
            "Switch to B" if self.current == "A" else "Switch to A"
        )

    def _load_current(self, position_ms: int, autoplay: bool) -> None:
        if not self.player:
            return
        url = self._urls.get(self.current)
        if url is None:
            return
        self._pending_ms = max(0, int(position_ms))
        self.player.setSource(url)
        if autoplay:
            self.player.play()

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.LoadedMedia and self._pending_ms:
            self.player.setPosition(self._pending_ms)
            self._pending_ms = 0
            if self._was_playing:
                self.player.play()

    def _toggle_play(self) -> None:
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            if self.player.source().isEmpty() and "A" in self._urls:
                self._load_current(self.player.position(), autoplay=False)
            self.player.play()

    def _on_position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_label.setText(f"{_clock(ms)} / {_clock(self.player.duration())}")

    def _on_duration(self, ms: int) -> None:
        self.slider.setRange(0, max(0, ms))
        self.time_label.setText(f"{_clock(self.player.position())} / {_clock(ms)}")

    def _on_state(self, state) -> None:
        self.play_button.setText(
            "Pause" if state == QMediaPlayer.PlayingState else "Play"
        )

    def _on_error(self, *_args) -> None:
        message = self.player.errorString() if self.player else "unknown error"
        self.status.setText(f"Playback error: {message}")
