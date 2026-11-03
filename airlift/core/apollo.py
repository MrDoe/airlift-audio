"""Apollo model wrapper: device selection, loading, chunked restoration.

The model implementation lives in ``airlift/third_party/apollo`` (copied
unmodified from github.com/JusperLee/Apollo, CC BY-SA 4.0). Airlift's own
code here is MIT; see third_party/apollo/README.md for attribution.
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path
from typing import Callable

import numpy as np

from .audio import SAMPLE_RATE

APOLLO_REPO = "JusperLee/Apollo"
APOLLO_FILE = "pytorch_model.bin"

_THIRD_PARTY = Path(__file__).resolve().parent.parent / "third_party" / "apollo"
if str(_THIRD_PARTY) not in sys.path:
    sys.path.insert(0, str(_THIRD_PARTY))

Progress = Callable[[str, float], None]
CancelCheck = Callable[[], bool]


class CancelledError(Exception):
    """Raised when the user cancels a running job."""


def resolve_device(preference: str = "auto") -> str:
    import torch

    if preference == "cpu":
        return "cpu"
    if preference == "cuda":
        # Ships with a CPU-only torch wheel; explicitly flag the missing build.
        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA was requested but this build ships CPU-only torch. "
                "Reinstall torch with CUDA wheels (e.g. cu128) or use --device cpu."
            )
        return "cuda"
    if preference == "mps":
        if not torch.backends.mps.is_available():
            raise RuntimeError("MPS was requested but is not available on this machine.")
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def describe_device(device: str) -> str:
    import torch

    if device == "cuda":
        return f"CUDA — {torch.cuda.get_device_name(0)}"
    if device == "mps":
        return "Apple Metal (MPS)"
    return "CPU"


def _edge_weights(length: int, overlap: int, fade_in: bool, fade_out: bool) -> np.ndarray:
    """Linear ramps on chunk edges, flat in the middle (normalized OLA)."""
    weights = np.ones(length, dtype=np.float32)
    fade = min(overlap, length)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        if fade_in:
            weights[:fade] = ramp
        if fade_out:
            weights[-fade:] = ramp[::-1]
    return weights


def _chunk_starts(total: int, chunk: int, overlap: int) -> list[int]:
    hop = chunk - overlap
    starts = [0]
    while starts[-1] + chunk < total:
        starts.append(starts[-1] + hop)
    return starts


class ApolloRestorer:
    """Loads Apollo once and restores any number of tracks."""

    def __init__(
        self,
        device: str = "auto",
        checkpoint: str | Path | None = None,
        repo_id: str = APOLLO_REPO,
    ) -> None:
        self.device = resolve_device(device)
        self.checkpoint = str(checkpoint) if checkpoint else None
        self.repo_id = repo_id
        self.model = None

    # -- loading ---------------------------------------------------------
    def load(self, progress: Progress | None = None) -> None:
        if self.model is not None:
            return
        import torch

        def report(stage: str, fraction: float) -> None:
            if progress:
                progress(stage, fraction)

        if self.checkpoint and Path(self.checkpoint).is_file():
            path = Path(self.checkpoint)
            report("Loading model", 0.4)
        else:
            from huggingface_hub import hf_hub_download

            report("Downloading model (66 MB, first run only)", 0.05)
            path = Path(
                hf_hub_download(self.repo_id, self.checkpoint or APOLLO_FILE)
            )
            report("Loading model", 0.6)

        import look2hear.models

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            model = look2hear.models.BaseModel.from_pretrain(
                str(path), sr=SAMPLE_RATE, win=20, feature_dim=256, layer=6
            )
        model.to(self.device).eval()
        model.requires_grad_(False)
        self.model = model
        report("Model ready", 1.0)

    def ensure_loaded(self, progress: Progress | None = None) -> None:
        if self.model is None:
            self.load(progress)

    # -- inference -------------------------------------------------------
    def restore(
        self,
        audio: np.ndarray,
        *,
        chunk_seconds: float = 6.0,
        overlap_seconds: float = 1.0,
        pad_seconds: float = 1.0,
        batch_size: int = 2,
        progress: Progress | None = None,
        cancel: CancelCheck | None = None,
    ) -> np.ndarray:
        """Restore a (samples, 2) float32 track at 44.1 kHz."""
        import torch
        import torch.nn.functional as F

        if self.model is None:
            raise RuntimeError("Model is not loaded; call load() first.")
        if audio.ndim != 2 or audio.shape[1] != 2:
            raise ValueError("Expected (samples, 2) stereo audio.")

        total = audio.shape[0]
        chunk = int(round(chunk_seconds * SAMPLE_RATE))
        overlap = int(round(overlap_seconds * SAMPLE_RATE))
        pad = int(round(pad_seconds * SAMPLE_RATE))
        batch_size = max(1, int(batch_size))
        if chunk <= 0:
            raise ValueError("Chunk length must be positive.")
        if overlap * 2 > chunk:
            raise ValueError("Overlap must not exceed half the chunk length.")

        tensor = torch.from_numpy(np.ascontiguousarray(audio.T)).unsqueeze(0)

        def check_cancel() -> None:
            if cancel and cancel():
                raise CancelledError("Cancelled")

        # Short files: one forward pass, no seam handling needed.
        if total <= chunk:
            check_cancel()
            with torch.inference_mode():
                out = self.model(tensor.to(self.device)).detach().float().cpu()
            if progress:
                progress("Restoring", 1.0)
            return out.squeeze(0).numpy().T

        starts = _chunk_starts(total, chunk, overlap)
        out_sum = np.zeros((total, 2), dtype=np.float32)
        weight_sum = np.zeros(total, dtype=np.float32)
        padded_len = chunk + 2 * pad

        for batch_start in range(0, len(starts), batch_size):
            check_cancel()
            group = starts[batch_start:batch_start + batch_size]
            pieces = []
            places = []
            for start in group:
                end = min(start + chunk, total)
                valid = end - start
                # Real audio padding at both sides; the file edges borrow
                # context from inside the file rather than from silence.
                padded_start = max(0, start - pad)
                if pad and end == total:
                    padded_start = max(0, total - padded_len)
                piece = tensor[..., padded_start:padded_start + padded_len]
                if piece.shape[-1] < padded_len:
                    piece = F.pad(piece, (0, padded_len - piece.shape[-1]))
                pieces.append(piece)
                places.append((start, valid, padded_start))

            batch = torch.cat(pieces, dim=0).to(self.device)
            with torch.inference_mode():
                restored = self.model(batch).detach().float().cpu().numpy()

            for index, (start, valid, padded_start) in enumerate(places):
                offset = start - padded_start
                segment = restored[index][:, offset:offset + valid]
                weights = _edge_weights(
                    valid,
                    overlap,
                    fade_in=batch_start + index > 0,
                    fade_out=batch_start + index < len(starts) - 1,
                )
                out_sum[start:start + valid] += segment.T * weights[:, None]
                weight_sum[start:start + valid] += weights

            if progress:
                done = batch_start + len(group)
                progress("Restoring", min(1.0, done / len(starts)))

        if np.any(weight_sum <= 0):
            raise RuntimeError("Chunk overlap-add left samples uncovered.")
        return out_sum / weight_sum[:, None]
