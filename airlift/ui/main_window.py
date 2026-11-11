"""Main window: settings rail, queue, comparison and A/B listening."""

from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path

import soundfile as sf
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
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
from ..core.pipeline import AUDIO_SUFFIXES, EnhanceOptions, EnhanceResult
from ..core.stems import has_demucs
from .icons import icon
from .player import MULTIMEDIA, ABPlayer
from .theme import ACCENT, DANGER, MUTED, SUCCESS, WARNING

COLUMNS = ["File", "Duration", "Status", "Progress"]
PRESETS = {
    "Restore": (2.5, 9_000),
    "Gentle": (1.5, 10_000),
    "Raw": (0.0, 9_000),
}
CHIP_STATES = {"pending", "queued", "processing", "done", "failed", "cancelled", "missing"}


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class StatusChip(QLabel):
    """Compact row status with a themeable state property."""

    def __init__(self, text: str = "Pending") -> None:
        super().__init__()
        self.setObjectName("statusChip")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self.set_state(text)

    def set_state(self, text: str, tooltip: str = "") -> None:
        self.setText(text)
        self.setToolTip(tooltip)
        state = text.strip().lower()
        if state not in CHIP_STATES:
            state = "processing" if text else "pending"
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_ID)
        self.jobs: list[Path] = []
        self.results: dict[str, EnhanceResult] = {}
        self.worker = None
        self.restorer: ApolloRestorer | None = None
        self._active_rows: list[int] = []
        self._pending_paths: list[Path] = []
        self._durations: dict[str, float] = {}
        self._progress_bars: dict[str, QProgressBar] = {}
        self._playing_row: int | None = None
        self._playing_path: str | None = None
        self._running = False
        self._loading_settings = False
        self._rail_visible = True
        self.demucs_python = ""

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1240, 840)
        self.setMinimumSize(1000, 640)
        self.setAcceptDrops(True)

        self._build_actions()
        self._build_ui()
        self._build_menu()
        self._load_settings()
        self._update_queue_ui()
        QTimer.singleShot(0, self._update_demucs_label)
        self._log(f"{APP_NAME} {__version__} ready.")

    # ------------------------------------------------------------------ UI
    def _build_actions(self) -> None:
        self.act_add = QAction(icon("plus"), "Add files", self)
        self.act_add.setShortcut(QKeySequence.Open)
        self.act_add.triggered.connect(self.add_files)

        self.act_folder = QAction(icon("folder"), "Add folder", self)
        self.act_folder.setShortcut("Ctrl+Shift+O")
        self.act_folder.triggered.connect(self.add_folder)

        self.act_remove = QAction(icon("trash"), "Remove", self)
        self.act_remove.setShortcut(QKeySequence.Delete)
        self.act_remove.triggered.connect(self.remove_selected)

        self.act_clear = QAction(icon("close"), "Clear queue", self)
        self.act_clear.triggered.connect(self.clear_all)

        self.act_clear_done = QAction(icon("check"), "Clear completed", self)
        self.act_clear_done.triggered.connect(self.clear_completed)

        self.act_retry = QAction(icon("retry"), "Retry failed", self)
        self.act_retry.triggered.connect(self.retry_failed)

        self.act_start = QAction(icon("play", ACCENT), "Enhance", self)
        self.act_start.setShortcut("Ctrl+Return")
        self.act_start.triggered.connect(self.start_batch)

        self.act_start_selected = QAction(icon("play", ACCENT), "Enhance selected", self)
        self.act_start_selected.triggered.connect(self.enhance_selected)

        self.act_cancel = QAction(icon("stop", DANGER), "Cancel", self)
        self.act_cancel.triggered.connect(self.cancel_batch)

        self.act_stems = QAction(icon("layers"), "Separate stems", self)
        self.act_stems.setShortcut("Ctrl+Shift+S")
        self.act_stems.setToolTip("Split into vocals and instrumental with Demucs")
        self.act_stems.triggered.connect(self.open_stem_dialog)

        self.act_play = QAction(icon("play", ACCENT), "Play / pause selected", self)
        self.act_play.triggered.connect(self.toggle_play_selected)

        self.act_stop = QAction(icon("stop"), "Stop playback", self)
        self.act_stop.setShortcut("Ctrl+.")
        self.act_stop.triggered.connect(self.stop_playback)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)
        body_layout.setSpacing(12)

        self.settings_panel = self._build_settings_rail()
        self.rail_scroll = QScrollArea()
        self.rail_scroll.setWidgetResizable(True)
        self.rail_scroll.setFrameShape(QFrame.NoFrame)
        self.rail_scroll.setFixedWidth(320)
        self.rail_scroll.setWidget(self.settings_panel)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.rail_scroll)
        self.main_splitter.addWidget(self._build_workspace())
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([320, 920])
        body_layout.addWidget(self.main_splitter)
        root.addWidget(body, 1)
        self.setCentralWidget(central)

        self.overall = QProgressBar()
        self.overall.setObjectName("overall")
        self.overall.setFixedWidth(220)
        self.overall.setRange(0, 100)
        self.overall.setVisible(False)
        self.status_label = QLabel("Ready")
        self.status_label.setProperty("role", "muted")
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

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("header")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        logo_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        logo = QLabel()
        if logo_path.is_file():
            pixmap = QPixmap(str(logo_path))
            logo.setPixmap(
                pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setProperty("role", "title")
        subtitle = QLabel("Local restoration for lossy and codec-damaged music")
        subtitle.setProperty("role", "subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        self.rail_toggle = QToolButton()
        self.rail_toggle.setIcon(icon("chevron-left"))
        self.rail_toggle.setToolTip("Show / hide settings")
        self.rail_toggle.clicked.connect(self.toggle_rail)
        layout.addWidget(self.rail_toggle)

        self.add_btn = QPushButton("Add files")
        self.add_btn.setIcon(icon("plus", "#E6EDF5"))
        self.add_btn.clicked.connect(self.add_files)
        layout.addWidget(self.add_btn)

        self.folder_btn = QToolButton()
        self.folder_btn.setIcon(icon("folder"))
        self.folder_btn.setToolTip("Add folder")
        self.folder_btn.clicked.connect(self.add_folder)
        layout.addWidget(self.folder_btn)

        self.enhance_btn = QPushButton("Enhance")
        self.enhance_btn.setProperty("variant", "primary")
        self.enhance_btn.setIcon(icon("play", "#06201C"))
        self.enhance_btn.setMinimumWidth(118)
        self.enhance_btn.clicked.connect(self.start_batch)
        layout.addWidget(self.enhance_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("variant", "danger")
        self.cancel_btn.setIcon(icon("stop", DANGER))
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_batch)
        layout.addWidget(self.cancel_btn)
        return frame

    def _build_settings_rail(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Restoration")
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch(1)
        self.preset_combo = QComboBox()
        for name in (*PRESETS, "Custom"):
            self.preset_combo.addItem(name, name)
        self.preset_combo.setFixedWidth(104)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        header.addWidget(self.preset_combo)

        self.reset_btn = QToolButton()
        self.reset_btn.setIcon(icon("retry"))
        self.reset_btn.setToolTip("Reset settings to defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)
        header.addWidget(self.reset_btn)
        layout.addLayout(header)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        air_row = QHBoxLayout()
        air_row.setSpacing(6)
        self.shelf_spin = QDoubleSpinBox()
        self.shelf_spin.setRange(0.0, 6.0)
        self.shelf_spin.setSingleStep(0.5)
        self.shelf_spin.setDecimals(1)
        self.shelf_spin.setSuffix(" dB")
        self.shelf_spin.setValue(2.5)
        self.shelf_spin.setToolTip(
            "High-shelf boost compensating Apollo's treble tilt. 0 dB = raw output."
        )
        self.shelf_spin.valueChanged.connect(self._mark_custom)
        air_row.addWidget(self.shelf_spin, 1)
        air_row.addWidget(QLabel("above"))
        self.shelf_freq = QSpinBox()
        self.shelf_freq.setRange(4_000, 16_000)
        self.shelf_freq.setSingleStep(500)
        self.shelf_freq.setSuffix(" Hz")
        self.shelf_freq.setValue(9_000)
        self.shelf_freq.valueChanged.connect(self._mark_custom)
        air_row.addWidget(self.shelf_freq, 1)
        form.addRow("Air shelf", air_row)

        self.format_combo = QComboBox()
        self.format_combo.addItem("WAV · 32-bit float", "wav")
        self.format_combo.addItem("FLAC · 24-bit", "flac")
        form.addRow("Format", self.format_combo)

        output_row = QHBoxLayout()
        output_row.setSpacing(6)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Same folder as source")
        self.output_edit.setClearButtonEnabled(True)
        output_row.addWidget(self.output_edit, 1)
        self.output_browse = QToolButton()
        self.output_browse.setIcon(icon("folder"))
        self.output_browse.setToolTip("Choose output folder")
        self.output_browse.clicked.connect(self.pick_output_dir)
        output_row.addWidget(self.output_browse)
        form.addRow("Output", output_row)

        self.same_folder = QCheckBox("Same folder as source")
        self.same_folder.toggled.connect(self._toggle_output_mode)
        form.addRow("", self.same_folder)

        self.device_combo = QComboBox()
        self.device_combo.addItem("Auto", "auto")
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("CUDA", "cuda")
        self.device_combo.addItem("Apple MPS", "mps")
        form.addRow("Device", self.device_combo)

        self.device_label = QLabel("")
        self.device_label.setProperty("role", "muted")
        self.device_label.setWordWrap(True)
        form.addRow("", self.device_label)

        demucs_row = QHBoxLayout()
        self.demucs_label = QLabel("Not configured")
        self.demucs_label.setProperty("role", "muted")
        self.demucs_label.setWordWrap(True)
        demucs_row.addWidget(self.demucs_label, 1)
        self.demucs_btn = QPushButton("Set…")
        self.demucs_btn.setProperty("variant", "ghost")
        self.demucs_btn.setToolTip("Choose a Python interpreter that can import demucs")
        self.demucs_btn.clicked.connect(self._pick_demucs_python)
        demucs_row.addWidget(self.demucs_btn)
        form.addRow("Demucs", demucs_row)

        layout.addLayout(form)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setText("Advanced")
        self.advanced_toggle.setIcon(icon("chevron-right"))
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)

        self.advanced_panel = QWidget()
        adv_grid = QGridLayout(self.advanced_panel)
        adv_grid.setContentsMargins(0, 0, 0, 0)
        adv_grid.setHorizontalSpacing(8)
        adv_grid.setVerticalSpacing(8)
        self.chunk_spin = self._seconds_spin(6.0, 2.0, 30.0)
        self.overlap_spin = self._seconds_spin(1.0, 0.0, 5.0)
        self.pad_spin = self._seconds_spin(1.0, 0.0, 5.0)
        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 8)
        self.batch_spin.setValue(2)
        adv_grid.addWidget(self.chunk_spin, 1, 0)
        adv_grid.addWidget(self.overlap_spin, 1, 1)
        adv_grid.addWidget(self.pad_spin, 1, 2)
        adv_grid.addWidget(self.batch_spin, 1, 3)
        for column, label in enumerate(("Chunk", "Overlap", "Pad", "Batch")):
            caption = QLabel(label)
            caption.setProperty("role", "muted")
            adv_grid.addWidget(caption, 0, column)
            adv_grid.setColumnStretch(column, 1)
        for spin in (self.chunk_spin, self.overlap_spin, self.pad_spin, self.batch_spin):
            spin.setMinimumWidth(0)
            spin.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.advanced_panel.setVisible(False)
        layout.addWidget(self.advanced_panel)

        layout.addStretch(1)
        return frame

    def _build_workspace(self) -> QWidget:
        self.work_splitter = QSplitter(Qt.Vertical)
        self.work_splitter.setChildrenCollapsible(False)
        self.work_splitter.addWidget(self._build_queue())
        self.work_splitter.addWidget(self._build_detail())
        self.work_splitter.setStretchFactor(0, 3)
        self.work_splitter.setStretchFactor(1, 2)
        self.work_splitter.setSizes([430, 320])
        return self.work_splitter

    def _build_queue(self) -> QWidget:
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("Queue")
        title.setProperty("role", "title")
        header.addWidget(title)
        self.count_label = QLabel("0 files")
        self.count_label.setProperty("role", "muted")
        header.addWidget(self.count_label)
        self.duration_label = QLabel("")
        self.duration_label.setProperty("role", "mono")
        header.addWidget(self.duration_label)
        header.addStretch(1)

        self.play_btn = QPushButton("Play")
        self.play_btn.setIcon(icon("play", ACCENT))
        self.play_btn.setToolTip("Play / pause the selected file")
        self.play_btn.clicked.connect(self.toggle_play_selected)
        header.addWidget(self.play_btn)

        self.separate_btn = QPushButton("Separate stems")
        self.separate_btn.setProperty("variant", "ghost")
        self.separate_btn.setIcon(icon("layers"))
        self.separate_btn.clicked.connect(self.open_stem_dialog)
        header.addWidget(self.separate_btn)

        self.remove_btn = QToolButton()
        self.remove_btn.setIcon(icon("trash"))
        self.remove_btn.setToolTip("Remove selected files")
        self.remove_btn.clicked.connect(self.remove_selected)
        header.addWidget(self.remove_btn)

        self.clear_btn = QToolButton()
        self.clear_btn.setIcon(icon("close"))
        self.clear_btn.setToolTip("Clear the queue")
        self.clear_btn.clicked.connect(self.clear_all)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.queue_stack = QStackedWidget()
        self.empty_state = self._build_empty_state()
        self.table = self._build_table()
        self.queue_stack.addWidget(self.empty_state)
        self.queue_stack.addWidget(self.table)
        layout.addWidget(self.queue_stack, 1)
        return wrap

    def _build_empty_state(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("emptyState")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        layout.addStretch(1)

        icon_label = QLabel()
        icon_label.setPixmap(icon("file", MUTED, 46).pixmap(46, 46))
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel("Drop audio files here")
        title.setProperty("role", "title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("WAV · FLAC · MP3 · M4A · OGG · Opus · AAC · AIFF")
        subtitle.setProperty("role", "muted")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        add_btn = QPushButton("Add files")
        add_btn.setProperty("variant", "primary")
        add_btn.setIcon(icon("plus", "#06201C"))
        add_btn.clicked.connect(self.add_files)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(add_btn)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return frame

    def _build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(COLUMNS))
        table.setHorizontalHeaderLabels(COLUMNS)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideMiddle)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(42)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_queue_menu)
        table.cellDoubleClicked.connect(self._on_row_double_clicked)
        table.itemSelectionChanged.connect(self._on_selection)
        space = QShortcut(QKeySequence(Qt.Key_Space), table)
        space.setContext(Qt.WidgetWithChildrenShortcut)
        space.activated.connect(self.toggle_play_selected)
        head = table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(1, QHeaderView.Fixed)
        head.setSectionResizeMode(2, QHeaderView.Fixed)
        head.setSectionResizeMode(3, QHeaderView.Fixed)
        table.setColumnWidth(1, 84)
        table.setColumnWidth(2, 104)
        table.setColumnWidth(3, 128)
        for column, alignment in (
            (0, Qt.AlignLeft | Qt.AlignVCenter),
            (1, Qt.AlignRight | Qt.AlignVCenter),
            (2, Qt.AlignCenter),
            (3, Qt.AlignCenter),
        ):
            item = table.horizontalHeaderItem(column)
            if item is not None:
                item.setTextAlignment(alignment)
        return table

    def _build_detail(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Comparison")
        title.setProperty("role", "title")
        header.addWidget(title)
        self.detail_title = QLabel("")
        self.detail_title.setProperty("role", "muted")
        self.detail_title.setWordWrap(True)
        header.addWidget(self.detail_title, 1)
        layout.addLayout(header)

        self.detail_stack = QStackedWidget()
        empty = QLabel("Select a finished file to inspect its bands.")
        empty.setProperty("role", "muted")
        empty.setAlignment(Qt.AlignCenter)
        self.detail_stack.addWidget(empty)

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        self.band_table = QTableWidget(len(BAND_EDGES) - 1, 4)
        self.band_table.setHorizontalHeaderLabels(["Band", "Original", "Enhanced", "Δ"])
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.band_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.band_table.setAlternatingRowColors(True)
        self.band_table.setShowGrid(False)
        self.band_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.band_table.verticalHeader().setDefaultSectionSize(21)
        self.band_table.setMinimumHeight(60)
        self.band_table.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        labels = band_labels()
        for row, label in enumerate(labels):
            item = QTableWidgetItem(label)
            item.setForeground(QColor(MUTED))
            self.band_table.setItem(row, 0, item)
        content_layout.addWidget(self.band_table, 1)

        self.player = ABPlayer()
        self.player.playing_changed.connect(self._on_playing_changed)
        self.player.stopped.connect(self._on_player_stopped)
        self.player.source_changed.connect(self._on_player_source_changed)
        content_layout.addWidget(self.player)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.clip_seconds = QSpinBox()
        self.clip_seconds.setRange(5, 120)
        self.clip_seconds.setValue(40)
        self.clip_seconds.setSuffix(" s")
        self.clip_seconds.setToolTip("Length of the exported A/B comparison clip")
        buttons.addWidget(self.clip_seconds)

        self.export_ab_btn = QPushButton("Export A/B clip")
        self.export_ab_btn.setIcon(icon("file"))
        self.export_ab_btn.setEnabled(False)
        self.export_ab_btn.clicked.connect(self.export_ab)
        buttons.addWidget(self.export_ab_btn)

        self.reveal_btn = QPushButton("Open output folder")
        self.reveal_btn.setIcon(icon("external"))
        self.reveal_btn.setEnabled(False)
        self.reveal_btn.clicked.connect(self.reveal_output)
        buttons.addWidget(self.reveal_btn)

        self.copy_btn = QPushButton("Copy report")
        self.copy_btn.setIcon(icon("copy"))
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_report)
        buttons.addWidget(self.copy_btn)
        buttons.addStretch(1)
        content_layout.addLayout(buttons)

        self.detail_stack.addWidget(content)
        self.detail_stack.setCurrentIndex(0)
        layout.addWidget(self.detail_stack, 1)
        return panel

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.act_add)
        file_menu.addAction(self.act_folder)
        file_menu.addSeparator()
        file_menu.addAction(self.act_start)
        file_menu.addAction(self.act_start_selected)
        file_menu.addAction(self.act_cancel)
        file_menu.addSeparator()
        file_menu.addAction(self.act_retry)
        file_menu.addAction(self.act_clear_done)
        file_menu.addSeparator()
        file_menu.addAction(self.act_remove)
        file_menu.addAction(self.act_clear)
        file_menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        queue_menu = self.menuBar().addMenu("&Queue")
        queue_menu.addAction(self.act_play)
        queue_menu.addAction(self.act_stop)
        queue_menu.addSeparator()
        queue_menu.addAction(self.act_start_selected)
        queue_menu.addAction(self.act_stems)
        queue_menu.addSeparator()
        queue_menu.addAction(self.act_remove)
        queue_menu.addAction(self.act_clear)

        view_menu = self.menuBar().addMenu("&View")
        toggle_log = self.dock.toggleViewAction()
        toggle_log.setText("Activity log")
        view_menu.addAction(toggle_log)

        tools_menu = self.menuBar().addMenu("&Tools")
        tools_menu.addAction(self.act_stems)
        configure = QAction("Configure Demucs…", self)
        configure.triggered.connect(self._pick_demucs_python)
        tools_menu.addAction(configure)

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About Airlift Audio", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    @staticmethod
    def _seconds_spin(value: float, low: float, high: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setSingleStep(0.5)
        spin.setDecimals(1)
        spin.setSuffix(" s")
        spin.setValue(value)
        return spin

    # -------------------------------------------------------------- settings
    def _load_settings(self) -> None:
        s = self.settings
        self._loading_settings = True
        try:
            self.shelf_spin.setValue(float(s.value("shelf_db", 2.5)))
            self.shelf_freq.setValue(int(s.value("shelf_freq", 9000)))
            index = self.format_combo.findData(s.value("format", "wav"))
            self.format_combo.setCurrentIndex(max(0, index))
            self.device_combo.setCurrentIndex(
                max(0, self.device_combo.findData(s.value("device", "auto")))
            )
            self.output_edit.setText(str(s.value("output_dir", "")))
            self.output_edit.setCursorPosition(0)
            self.same_folder.setChecked(
                bool(s.value("same_folder", not self.output_edit.text().strip(), type=bool))
            )
            self.demucs_python = str(
                s.value("demucs_python", os.environ.get("AIRLIFT_DEMUCS_PYTHON", ""))
            )
            self.chunk_spin.setValue(float(s.value("chunk_seconds", 6.0)))
            self.overlap_spin.setValue(float(s.value("overlap_seconds", 1.0)))
            self.pad_spin.setValue(float(s.value("pad_seconds", 1.0)))
            self.batch_spin.setValue(int(s.value("batch_size", 2)))
            preset = str(s.value("preset", "Restore"))
            self.preset_combo.setCurrentIndex(
                max(0, self.preset_combo.findData(preset))
            )
            self.advanced_toggle.setChecked(
                bool(s.value("advanced", False, type=bool))
            )
            self.player.set_volume(float(s.value("volume", 0.9)))
            self._set_rail_visible(
                bool(s.value("show_rail", True, type=bool)), save=False
            )
            geometry = s.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
            main_state = s.value("main_splitter")
            if main_state:
                self.main_splitter.restoreState(main_state)
            if self._rail_visible and self.main_splitter.sizes()[0] < 200:
                self.main_splitter.setSizes([320, 900])
            work_state = s.value("work_splitter")
            if work_state:
                self.work_splitter.restoreState(work_state)
            header_state = s.value("queue_header")
            if header_state:
                self.table.horizontalHeader().restoreState(header_state)
            head = self.table.horizontalHeader()
            head.setSectionResizeMode(0, QHeaderView.Stretch)
            head.setSectionResizeMode(1, QHeaderView.Fixed)
            head.setSectionResizeMode(2, QHeaderView.Fixed)
            head.setSectionResizeMode(3, QHeaderView.Fixed)
            for column, minimum in ((1, 84), (2, 104), (3, 128)):
                self.table.setColumnWidth(column, minimum)
        finally:
            self._loading_settings = False
        self._toggle_output_mode(self.same_folder.isChecked())

    def _save_settings(self) -> None:
        s = self.settings
        s.setValue("shelf_db", self.shelf_spin.value())
        s.setValue("shelf_freq", self.shelf_freq.value())
        s.setValue("format", self.format_combo.currentData())
        s.setValue("output_dir", self.output_edit.text())
        s.setValue("same_folder", self.same_folder.isChecked())
        s.setValue("device", self.device_combo.currentData())
        s.setValue("demucs_python", self.demucs_python)
        s.setValue("chunk_seconds", self.chunk_spin.value())
        s.setValue("overlap_seconds", self.overlap_spin.value())
        s.setValue("pad_seconds", self.pad_spin.value())
        s.setValue("batch_size", self.batch_spin.value())
        s.setValue("preset", self.preset_combo.currentData())
        s.setValue("advanced", self.advanced_toggle.isChecked())
        s.setValue("volume", self.player.volume())
        s.setValue("show_rail", self._rail_visible)
        s.setValue("geometry", self.saveGeometry())
        s.setValue("main_splitter", self.main_splitter.saveState())
        s.setValue("work_splitter", self.work_splitter.saveState())
        s.setValue("queue_header", self.table.horizontalHeader().saveState())

    def _apply_preset(self, _index: int) -> None:
        if self._loading_settings:
            return
        name = self.preset_combo.currentData()
        if name not in PRESETS:
            return
        shelf, freq = PRESETS[name]
        self._loading_settings = True
        try:
            self.shelf_spin.setValue(shelf)
            self.shelf_freq.setValue(freq)
        finally:
            self._loading_settings = False
        self._log(f"Preset: {name} ({shelf:.1f} dB above {freq} Hz).")

    def _mark_custom(self, *_args) -> None:
        if self._loading_settings:
            return
        index = self.preset_combo.findData("Custom")
        if index >= 0 and self.preset_combo.currentIndex() != index:
            self.preset_combo.setCurrentIndex(index)

    def _toggle_output_mode(self, same_folder: bool) -> None:
        self.output_edit.setEnabled(not same_folder)
        self.output_browse.setEnabled(not same_folder)
        if same_folder:
            self.output_edit.clear()

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setIcon(
            icon("chevron-down" if checked else "chevron-right")
        )

    def toggle_rail(self) -> None:
        self._set_rail_visible(not self.rail_scroll.isVisible())

    def _set_rail_visible(self, visible: bool, save: bool = True) -> None:
        self._rail_visible = visible
        self.rail_scroll.setVisible(visible)
        if visible and self.main_splitter.sizes()[0] < 200:
            self.main_splitter.setSizes([320, 900])
        self.rail_toggle.setIcon(
            icon("chevron-left" if visible else "chevron-right")
        )
        if save:
            self.settings.setValue("show_rail", visible)

    def reset_defaults(self) -> None:
        self._loading_settings = True
        try:
            self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData("Restore")))
            self.shelf_spin.setValue(2.5)
            self.shelf_freq.setValue(9_000)
            self.format_combo.setCurrentIndex(max(0, self.format_combo.findData("wav")))
            self.same_folder.setChecked(True)
            self.output_edit.clear()
            self.device_combo.setCurrentIndex(max(0, self.device_combo.findData("auto")))
            self.chunk_spin.setValue(6.0)
            self.overlap_spin.setValue(1.0)
            self.pad_spin.setValue(1.0)
            self.batch_spin.setValue(2)
            self.player.set_volume(0.9)
        finally:
            self._loading_settings = False
        self._toggle_output_mode(True)
        self._log("Settings reset to defaults.")

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
            self._log(f"Added {added} file(s).")
            if self.table.currentRow() < 0 and self.table.rowCount() > 0:
                self.table.selectRow(0)
        elif paths:
            self._log("No new audio files found (unsupported or duplicate).")
        self._update_queue_ui()

    def open_stem_dialog(self) -> None:
        if self._running:
            return
        rows = self.selected_rows()
        if rows:
            files = [self.jobs[row] for row in rows if 0 <= row < len(self.jobs)]
        else:
            files = list(self.jobs)
        if not files:
            QMessageBox.information(self, APP_NAME, "Add audio files to the queue first.")
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
        self._update_demucs_label()

    def _add_stems(self, paths: list[str]) -> None:
        self._add_paths([Path(path) for path in paths])
        self._log(f"Added {len(paths)} separated stem(s) to the queue.")

    def _pick_demucs_python(self) -> None:
        start = str(Path(self.demucs_python).parent) if self.demucs_python else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a Python interpreter with Demucs", start, "All files (*)"
        )
        if not path:
            return
        self.demucs_python = path
        self._update_demucs_label()
        if not has_demucs(path):
            QMessageBox.warning(
                self,
                APP_NAME,
                "This interpreter cannot import demucs.\n\n"
                'Install it with: "pip install demucs"\n'
                "or choose an environment that already has demucs and a matching torchaudio.",
            )
        else:
            self._log(f"Demucs interpreter: {path}")

    def _update_demucs_label(self) -> None:
        path = self.demucs_python.strip()
        if not path:
            text, role, tip = "Not configured", "muted", "Set an interpreter that can import demucs."
        elif has_demucs(path):
            text, role, tip = "Ready", "accent", path
        else:
            text, role, tip = "Not found", "danger", path
        self.demucs_label.setText(text)
        self.demucs_label.setToolTip(f"{tip}\n{path}" if path else tip)
        self.demucs_label.setProperty("role", role)
        self.demucs_label.style().unpolish(self.demucs_label)
        self.demucs_label.style().polish(self.demucs_label)

    # ---------------------------------------------------------------- queue
    def _append_row(self, path: Path) -> None:
        row = self.table.rowCount()
        key = str(path)
        self.jobs.append(path)
        self.table.insertRow(row)

        name = QTableWidgetItem(path.name)
        name.setIcon(icon("file", MUTED, 14))
        name.setToolTip(str(path))
        name.setData(Qt.UserRole, key)
        self.table.setItem(row, 0, name)

        seconds = 0.0
        duration = "–"
        try:
            info = sf.info(str(path))
            seconds = info.frames / info.samplerate if info.samplerate else 0.0
            duration = _fmt_duration(seconds)
        except Exception:  # noqa: BLE001, S110
            pass
        self._durations[key] = seconds
        dur_item = QTableWidgetItem(duration)
        dur_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 1, dur_item)

        chip = StatusChip("Pending" if path.is_file() else "Missing")
        if not path.is_file():
            chip.setToolTip("File no longer exists")
        self.table.setCellWidget(row, 2, chip)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        self._progress_bars[key] = bar
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(8, 16, 8, 16)
        holder_layout.addWidget(bar)
        self.table.setCellWidget(row, 3, holder)

    def _row_progress(self, row: int) -> QProgressBar | None:
        if 0 <= row < len(self.jobs):
            return self._progress_bars.get(str(self.jobs[row]))
        return None

    def _status_text(self, row: int) -> str:
        chip = self.table.cellWidget(row, 2)
        return chip.text() if isinstance(chip, QLabel) else ""

    def _set_status(
        self, row: int, text: str, tooltip: str = "", color: str | None = None
    ) -> None:
        chip = self.table.cellWidget(row, 2)
        if not isinstance(chip, StatusChip):
            chip = StatusChip(text)
            self.table.setCellWidget(row, 2, chip)
        chip.set_state(text, tooltip)
        if color:
            chip.setStyleSheet(f"color: {color};")

    def _update_queue_ui(self) -> None:
        count = len(self.jobs)
        self.count_label.setText(f"{count} file" + ("s" if count != 1 else ""))
        total = sum(self._durations.get(str(path), 0.0) for path in self.jobs)
        self.duration_label.setText(f"· {_fmt_duration(total)} total" if total else "")
        self.queue_stack.setCurrentWidget(self.table if count else self.empty_state)
        self._sync_actions()
        self._update_play_button()

    def _sync_actions(self) -> None:
        has_jobs = bool(self.jobs)
        running = self._running
        enabled = has_jobs and not running
        for action in (
            self.act_start,
            self.act_start_selected,
            self.act_stems,
            self.act_remove,
            self.act_clear,
        ):
            action.setEnabled(enabled)
        any_done = any(str(path) in self.results for path in self.jobs)
        any_failed = any(
            self._status_text(row) == "Failed" for row in range(len(self.jobs))
        )
        self.act_clear_done.setEnabled(enabled and any_done)
        self.act_retry.setEnabled(enabled and any_failed)
        self.act_add.setEnabled(not running)
        self.act_folder.setEnabled(not running)
        self.act_cancel.setEnabled(running)
        self.act_cancel.setVisible(running)

        current = self.table.currentRow()
        has_current = 0 <= current < len(self.jobs)
        self.act_play.setEnabled(has_current and MULTIMEDIA)
        self.act_stop.setEnabled(self.player.has_media() and MULTIMEDIA)

        self.add_btn.setEnabled(not running)
        self.folder_btn.setEnabled(not running)
        self.enhance_btn.setEnabled(enabled)
        self.cancel_btn.setVisible(running)
        self.cancel_btn.setEnabled(running)
        self.play_btn.setEnabled(has_current and MULTIMEDIA)
        self.separate_btn.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled)
        self.clear_btn.setEnabled(enabled)
        self.settings_panel.setEnabled(not running)
        self.reset_btn.setEnabled(not running)

    def _update_play_button(self) -> None:
        row = self.table.currentRow()
        has_current = 0 <= row < len(self.jobs)
        current_key = str(self.jobs[row]) if has_current else None
        playing = bool(
            current_key
            and current_key == self._playing_path
            and self.player.is_playing()
        )
        self.play_btn.setText("Pause" if playing else "Play")
        self.play_btn.setIcon(
            icon("pause", ACCENT) if playing else icon("play", ACCENT)
        )
        self.act_play.setText("Pause selected" if playing else "Play / pause selected")

    def _update_playback_status(self) -> None:
        if not self._playing_path:
            return
        name = Path(self._playing_path).name
        label = "Enhanced" if self.player.current == "B" else "Original"
        self.status_label.setText(f"Playing: {name} · {label}")

    def _set_playing_row(self, row: int | None) -> None:
        if self._playing_row is not None and 0 <= self._playing_row < self.table.rowCount():
            item = self.table.item(self._playing_row, 0)
            if item is not None:
                item.setIcon(icon("file", MUTED, 14))
        if row is not None and 0 <= row < self.table.rowCount():
            item = self.table.item(row, 0)
            if item is not None:
                item.setIcon(icon("play", ACCENT, 14))
        self._playing_row = row

    def selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectedIndexes()})

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.jobs):
            self.table.selectRow(row)
            self.toggle_play_selected()

    def _show_queue_menu(self, pos) -> None:
        if self._running:
            return
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        if row not in self.selected_rows():
            self.table.selectRow(row)
        menu = QMenu(self)

        play = menu.addAction(
            icon("pause" if self.player.is_playing() else "play", ACCENT),
            "Pause" if self.player.is_playing() else "Play",
        )
        play.triggered.connect(self.toggle_play_selected)
        enhance = menu.addAction(icon("play"), "Enhance selected")
        enhance.triggered.connect(self.enhance_selected)
        stems = menu.addAction(icon("layers"), "Separate stems")
        stems.triggered.connect(self.open_stem_dialog)
        menu.addSeparator()

        result = self.results.get(str(self.jobs[row]))
        open_out = menu.addAction(icon("external"), "Open output folder")
        open_out.setEnabled(result is not None and result.output.exists())
        open_out.triggered.connect(self.reveal_output)
        copy_path = menu.addAction(icon("copy"), "Copy path")
        copy_path.triggered.connect(lambda: self._copy_text(str(self.jobs[row])))
        menu.addSeparator()
        retry = menu.addAction(icon("retry"), "Retry failed")
        retry.setEnabled(self._status_text(row) == "Failed")
        retry.triggered.connect(self.retry_failed)
        remove = menu.addAction(icon("trash"), "Remove")
        remove.triggered.connect(self.remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _copy_text(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self._log("Copied to clipboard.")

    def play_selected(self) -> None:
        self.toggle_play_selected()

    def toggle_play_selected(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.jobs)):
            return
        path = self.jobs[row]
        key = str(path)
        if not path.is_file():
            self._set_status(row, "Missing", str(path))
            self.status_label.setText(f"Missing file: {path.name}")
            return

        if key == self._playing_path:
            self.player.toggle_play()
            self._update_play_button()
            return

        if self.player.is_playing() or self.player.has_media():
            self.player.stop()
        self._playing_path = key
        self._set_playing_row(row)
        result = self.results.get(key)
        if result is not None:
            self._show_detail(row)
        else:
            self.player.set_sources(path, None)
        self.player.play()
        self._update_playback_status()
        self._update_play_button()

    def stop_playback(self) -> None:
        self.player.stop()

    def _on_playing_changed(self, _playing: bool) -> None:
        if self.player.is_playing() and self._playing_path is None:
            row = self.table.currentRow()
            if 0 <= row < len(self.jobs):
                self._playing_path = str(self.jobs[row])
                self._set_playing_row(row)
        self._update_play_button()
        if self.player.is_playing():
            self._update_playback_status()
        elif (
            self._playing_path
            and self.player.has_media()
            and self.player.player is not None
            and self.player.player.position() > 0
        ):
            name = Path(self._playing_path).name
            label = "Enhanced" if self.player.current == "B" else "Original"
            self.status_label.setText(f"Paused: {name} · {label}")

    def _on_player_stopped(self) -> None:
        self._set_playing_row(None)
        self._playing_path = None
        if not self._running:
            self.status_label.setText("Ready")
        self._update_play_button()

    def _on_player_source_changed(self, _source: str) -> None:
        if self._playing_path:
            self._update_playback_status()

    def _on_selection(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            if (
                self._playing_path
                and 0 <= row < len(self.jobs)
                and str(self.jobs[row]) != self._playing_path
            ):
                self.player.stop()
            self._show_detail(row)
        else:
            self._clear_detail()
        self._update_play_button()
        self._sync_actions()

    def remove_selected(self) -> None:
        if self._running:
            return
        rows = self.selected_rows()
        if not rows:
            return
        if len(rows) > 1:
            answer = QMessageBox.question(
                self,
                APP_NAME,
                f"Remove {len(rows)} files from the queue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if self._playing_row in rows:
            self.player.stop()
        for row in sorted(rows, reverse=True):
            key = str(self.jobs[row])
            self.results.pop(key, None)
            self._durations.pop(key, None)
            self._progress_bars.pop(key, None)
            self.jobs.pop(row)
            self.table.removeRow(row)
        self._clear_detail()
        self._update_queue_ui()

    def clear_all(self) -> None:
        if self._running or not self.jobs:
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            "Clear the entire queue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.player.stop()
        self.jobs.clear()
        self.results.clear()
        self._durations.clear()
        self._progress_bars.clear()
        self.table.setRowCount(0)
        self._update_queue_ui()
        self._clear_detail()

    def clear_completed(self) -> None:
        if self._running:
            return
        rows = [i for i, path in enumerate(self.jobs) if str(path) in self.results]
        if not rows:
            QMessageBox.information(self, APP_NAME, "No completed files in the queue.")
            return
        answer = QMessageBox.question(
            self,
            APP_NAME,
            f"Remove {len(rows)} completed file(s) from the queue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if self._playing_row in rows:
            self.player.stop()
        for row in sorted(rows, reverse=True):
            key = str(self.jobs[row])
            self.results.pop(key, None)
            self._durations.pop(key, None)
            self._progress_bars.pop(key, None)
            self.jobs.pop(row)
            self.table.removeRow(row)
        self._clear_detail()
        self._update_queue_ui()

    def retry_failed(self) -> None:
        if self._running:
            return
        rows = [i for i in range(len(self.jobs)) if self._status_text(i) == "Failed"]
        if not rows:
            QMessageBox.information(self, APP_NAME, "No failed files to retry.")
            return
        for row in rows:
            key = str(self.jobs[row])
            self.results.pop(key, None)
            self._set_status(row, "Pending", "")
            bar = self._row_progress(row)
            if bar:
                bar.setValue(0)
        self._log(f"Reset {len(rows)} failed file(s) to pending.")
        self._update_queue_ui()

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

    def enhance_selected(self) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        self.start_batch(rows)

    def start_batch(self, rows: list[int] | None = None) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if rows is None:
            candidates = list(range(len(self.jobs)))
        else:
            candidates = [row for row in rows if 0 <= row < len(self.jobs)]
        pending = [row for row in candidates if str(self.jobs[row]) not in self.results]
        missing = [row for row in pending if not self.jobs[row].is_file()]
        for row in missing:
            self._set_status(row, "Missing", str(self.jobs[row]))
        pending = [row for row in pending if row not in missing]
        if not pending:
            if missing:
                QMessageBox.warning(self, APP_NAME, "The selected files no longer exist.")
            else:
                QMessageBox.information(
                    self, APP_NAME, "Everything selected is already done."
                )
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
            self.cancel_btn.setEnabled(False)
            self.status_label.setText("Cancelling…")

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._sync_actions()

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
        self._set_status(row, "Processing", f"{stage} · {fraction*100:.0f}%")
        done = sum(
            1 for r in self._active_rows if self._status_text(r) == "Done"
        )
        self.status_label.setText(
            f"File {min(done + 1, len(self._active_rows))} of "
            f"{len(self._active_rows)} · {stage}"
        )

    def _on_item_done(self, index: int, result: EnhanceResult) -> None:
        row = self._row_for_index(index)
        if row is None:
            return
        path = result.source
        self.results[str(path)] = result
        bar = self._row_progress(row)
        if bar:
            bar.setValue(100)
        self._set_status(row, "Done", str(result.output))
        self._log(
            f"Done: {path.name} → {result.output.name} "
            f"({result.elapsed:.1f}s, peak {result.peak:.1f} dBFS)"
        )
        if self.table.currentRow() == row and not self.player.is_playing():
            self._show_detail(row)
        self._update_queue_ui()

    def _on_item_failed(self, index: int, message: str) -> None:
        row = self._row_for_index(index)
        if row is None:
            return
        self._set_status(row, "Failed", message)
        self._log(f"Failed: {self.jobs[row].name}: {message}")
        bar = self._row_progress(row)
        if bar:
            bar.setValue(0)
        self._update_queue_ui()

    def _on_fatal(self, message: str) -> None:
        self._log(message)
        QMessageBox.critical(self, APP_NAME, message)

    def _on_batch_finished(self) -> None:
        if self.worker and self.worker.restorer is not None:
            self.restorer = self.worker.restorer
        cancelled = bool(self.worker and self.worker.cancelled)
        if cancelled:
            for row in self._active_rows:
                if self._status_text(row) not in {"Done", "Failed"}:
                    self._set_status(row, "Cancelled", "Batch cancelled")
        done = sum(1 for row in self._active_rows if self._status_text(row) == "Done")
        failed = sum(1 for row in self._active_rows if self._status_text(row) == "Failed")
        cancelled_count = sum(
            1 for row in self._active_rows if self._status_text(row) == "Cancelled"
        )
        self._set_running(False)
        self.overall.setVisible(False)
        if self.restorer:
            try:
                self.device_label.setText(describe_device(self.restorer.device))
            except Exception:  # noqa: BLE001
                self.device_label.setText(self.restorer.device)
        if cancelled:
            summary = f"Cancelled · {done} done · {cancelled_count} stopped"
            self._log("Batch cancelled.")
        elif failed:
            summary = f"Finished · {done} done · {failed} failed"
            self._log(f"Batch finished with {failed} failure(s).")
        else:
            summary = f"Done · {done} file(s) enhanced"
            self._log("Batch finished.")
        self.status_label.setText(summary)
        worker = self.worker
        QTimer.singleShot(0, lambda: self._release_worker(worker))

    def _release_worker(self, worker) -> None:
        if self.worker is worker:
            self.worker = None

    # --------------------------------------------------------------- detail
    def _clear_detail(self) -> None:
        self.detail_title.setText("")
        self.detail_stack.setCurrentIndex(0)
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
            self.detail_stack.setCurrentIndex(0)
            self.player.set_sources(path, None)
            self.export_ab_btn.setEnabled(False)
            self.reveal_btn.setEnabled(False)
            self.copy_btn.setEnabled(False)
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
                item.setForeground(QColor(SUCCESS if delta >= 0 else WARNING))
                self.band_table.setItem(i, 3, item)

        self.detail_stack.setCurrentIndex(1)
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

    def _current_result(self) -> EnhanceResult | None:
        row = self.table.currentRow()
        if 0 <= row < len(self.jobs):
            return self.results.get(str(self.jobs[row]))
        return None

    def reveal_output(self) -> None:
        result = self._current_result()
        if result and result.output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(result.output.parent)))

    def copy_report(self) -> None:
        result = self._current_result()
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
        result = self._current_result()
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
                original,
                enhanced,
                start_seconds=start,
                seconds=float(self.clip_seconds.value()),
                block_seconds=8.0,
                repeats=1,
            )
            sf.write(target, clip, SAMPLE_RATE, subtype="PCM_24")
        except Exception:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self,
                APP_NAME,
                "Could not export the A/B clip:\n\n" + traceback.format_exc(),
            )
            return
        QApplication.restoreOverrideCursor()
        self._log(f"A/B clip written: {target}")
        QMessageBox.information(self, APP_NAME, f"A/B clip written:\n{target}")

    def pick_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Output folder")
        if folder:
            self.output_edit.setText(folder)
            self.same_folder.setChecked(False)

    # ------------------------------------------------------------ misc/logs
    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")

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
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            self._add_paths(paths)
            event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        self.player.stop()
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(10_000)
        self._save_settings()
        super().closeEvent(event)
