"""A/B listening widget with a proper transport (play, pause, stop, volume)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .icons import icon

try:  # QtMultimedia ships with PySide6; tolerate stripped builds.
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    MULTIMEDIA = True
except Exception:  # noqa: BLE001 - platform dependent
    MULTIMEDIA = False


def _clock(ms: int) -> str:
    seconds = max(0, ms // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


class ABPlayer(QWidget):
    """Play original (A) or enhanced (B) at the same position."""

    playing_changed = Signal(bool)
    stopped = Signal()
    source_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current = "A"
        self._urls: dict[str, QUrl] = {}
        self._pending_ms = 0
        self._was_playing = False

        self.badge = QLabel("A · Original")
        self.badge.setProperty("role", "accent")
        self.badge.setMinimumWidth(96)

        self.play_button = QPushButton("Play")
        self.play_button.setProperty("variant", "primary")
        self.play_button.setIcon(icon("play", "#06201C"))
        self.play_button.setEnabled(False)
        self.play_button.setToolTip("Play / pause (Space)")

        self.stop_button = QPushButton()
        self.stop_button.setIcon(icon("stop", "#94A3B8"))
        self.stop_button.setToolTip("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.setProperty("variant", "ghost")

        self.swap_button = QPushButton("Switch to B")
        self.swap_button.setIcon(icon("swap"))
        self.swap_button.setEnabled(False)
        self.swap_button.setToolTip("Swap original/enhanced at the same position (B)")
        self.swap_button.setProperty("variant", "ghost")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setProperty("role", "mono")

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(90)
        self.volume_slider.setFixedWidth(76)
        self.volume_slider.setToolTip("Volume")
        self.volume_icon = QLabel()
        self.volume_icon.setPixmap(icon("volume", "#94A3B8", 16).pixmap(16, 16))

        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self.badge)
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.swap_button)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.time_label)
        controls.addWidget(self.volume_icon)
        controls.addWidget(self.volume_slider)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
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
            self.play_button.clicked.connect(self.toggle_play)
            self.stop_button.clicked.connect(self.stop)
            self.swap_button.clicked.connect(self.toggle)
            self.slider.sliderMoved.connect(self.player.setPosition)
            self.volume_slider.valueChanged.connect(self._on_volume)
            QShortcut(Qt.Key_Space, self, self.toggle_play)
            QShortcut(Qt.Key_B, self, self.toggle)
        else:
            self.player = None
            for widget in (
                self.play_button,
                self.stop_button,
                self.swap_button,
                self.slider,
                self.volume_slider,
                self.volume_icon,
            ):
                widget.setVisible(False)
            self.status.setText("Audio preview unavailable (QtMultimedia missing).")

    # -- public API ------------------------------------------------------
    def set_sources(self, original: Path | None, enhanced: Path | None) -> None:
        """Load A/B sources, stop current playback and keep the player ready."""
        self._urls.clear()
        if original and Path(original).is_file():
            self._urls["A"] = QUrl.fromLocalFile(str(Path(original)))
        if enhanced and Path(enhanced).is_file():
            self._urls["B"] = QUrl.fromLocalFile(str(Path(enhanced)))

        if self.player is not None:
            self.player.stop()

        available = bool(self._urls)
        if MULTIMEDIA:
            self.play_button.setEnabled(available)
            self.stop_button.setEnabled(available)
            self.swap_button.setEnabled("A" in self._urls and "B" in self._urls)
            self.slider.setEnabled(available)
        if not available:
            self.badge.setText("A · Original")
            self.status.setText("")
            self.time_label.setText("0:00 / 0:00")
            return

        self.current = "A" if "A" in self._urls else "B"
        self._update_badge()
        self._load_current(0, autoplay=False)
        self.source_changed.emit(self.current)
        if "A" not in self._urls:
            self.status.setText("Only the enhanced file is available.")
        elif "B" not in self._urls:
            self.status.setText("Original only · Space: play/pause")
        else:
            self.status.setText("Space: play/pause · B: switch A/B")

    def play(self) -> None:
        if not self.player or not self._urls:
            return
        if self.player.source().isEmpty():
            self._load_current(self.player.position(), autoplay=False)
        self.player.play()

    def pause(self) -> None:
        if self.player and self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()

    def stop(self) -> None:
        if not self.player:
            return
        self.player.stop()
        self.player.setPosition(0)
        self.time_label.setText("0:00 / 0:00")
        self.stopped.emit()
        self.playing_changed.emit(False)

    def toggle_play(self) -> None:
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.play()

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
        self.source_changed.emit(self.current)

    def is_playing(self) -> bool:
        return bool(
            self.player and self.player.playbackState() == QMediaPlayer.PlayingState
        )

    def set_volume(self, value: float) -> None:
        self.volume_slider.setValue(int(max(0.0, min(1.0, value)) * 100))

    def volume(self) -> float:
        return self.volume_slider.value() / 100.0

    def has_media(self) -> bool:
        return bool(self._urls)

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

    def _on_position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.time_label.setText(f"{_clock(ms)} / {_clock(self.player.duration())}")

    def _on_duration(self, ms: int) -> None:
        self.slider.setRange(0, max(0, ms))
        self.time_label.setText(f"{_clock(self.player.position())} / {_clock(ms)}")

    def _on_state(self, state) -> None:
        playing = state == QMediaPlayer.PlayingState
        self.play_button.setText("Pause" if playing else "Play")
        self.play_button.setIcon(
            icon("pause", "#06201C") if playing else icon("play", "#06201C")
        )
        self.playing_changed.emit(playing)

    def _on_volume(self, value: int) -> None:
        if getattr(self, "audio", None) is not None:
            self.audio.setVolume(value / 100.0)

    def _on_error(self, *_args) -> None:
        message = self.player.errorString() if self.player else "unknown error"
        self.status.setText(f"Playback error: {message}")
