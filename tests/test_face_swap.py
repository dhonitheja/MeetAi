import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from backend.face.face_swap_engine import FaceSwapEngine


def test_process_frame_no_target_returns_original():
    """process_frame returns original frame unchanged when no target set."""
    engine = FaceSwapEngine()
    # Don't call load() - test no-target path only
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Manually set face_analyzer to a mock so it doesn't crash
    engine.face_analyzer = MagicMock()
    result = engine.process_frame(frame)
    assert np.array_equal(result, frame), "Should return original frame unchanged"


def test_clear_target_sets_none():
    """clear_target() sets _target_face to None."""
    engine = FaceSwapEngine()
    engine._target_face = MagicMock()
    engine.clear_target()
    assert engine._target_face is None


def test_no_disk_write_in_set_target_face():
    """set_target_face() never writes to disk."""
    engine = FaceSwapEngine()
    engine.face_analyzer = MagicMock()
    engine.face_analyzer.get.return_value = []  # no face found

    import builtins

    original_open = builtins.open
    write_calls = []

    def mock_open(file, mode="r", *args, **kwargs):
        if any(m in mode for m in ("w", "wb", "a", "ab", "x")):
            write_calls.append((file, mode))
        return original_open(file, mode, *args, **kwargs)

    # Minimal valid PNG bytes (1x1 white pixel)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDAT\x08\x1dc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
        b"\x9f\xca-\x13\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with patch("builtins.open", mock_open):
        engine.set_target_face(png_bytes)

    assert write_calls == [], f"Unexpected disk writes: {write_calls}"


def test_unload_clears_all_models():
    """unload() sets all model references to None."""
    engine = FaceSwapEngine()
    engine.face_analyzer = MagicMock()
    engine.swapper = MagicMock()
    engine.enhancer = MagicMock()
    engine._target_face = MagicMock()
    engine.unload()
    assert engine.face_analyzer is None
    assert engine.swapper is None
    assert engine.enhancer is None
    assert engine._target_face is None
