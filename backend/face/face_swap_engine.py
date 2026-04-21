from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any
import cv2
try:
    import insightface
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
except ImportError:
    insightface = None
    FaceAnalysis = None
    HAS_INSIGHTFACE = False

import numpy as np
import onnxruntime as ort

try:
    from gfpgan import GFPGANer
    HAS_GFPGAN = True
except ImportError:
    GFPGANer = None
    HAS_GFPGAN = False


logger = logging.getLogger(__name__)

MODEL_DIR = Path("./models/insightface")
INSWAPPER_PATH = MODEL_DIR / "inswapper_128.onnx"


class FaceSwapEngine:
    """
    Real-time face swap engine using InsightFace + inswapper_128.

    Pipeline per frame:
      webcam frame -> detect faces -> swap with target embedding
      -> GFPGAN enhance -> output frame

    Runs at 24fps+ on NVIDIA RTX 2060 with CUDA EP.
    All face data processed in memory - no frames or images saved to disk.
    """

    def __init__(self) -> None:
        """Initialize model references and in-memory session state."""
        self.face_analyzer: FaceAnalysis | None = None
        self.swapper: Any = None
        self.enhancer: Any = None
        self._lock = threading.Lock()
        self._target_face: Any = None

    def load(self) -> None:
        """
        Load all models. Call once at app startup.
        buffalo_l downloads automatically on first run (~300MB).
        inswapper_128.onnx must be pre-placed at MODEL_DIR.
        Raises FileNotFoundError if inswapper_128.onnx is missing.
        """
        self.face_analyzer = FaceAnalysis(
            name="buffalo_l",
            root=str(MODEL_DIR),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self.face_analyzer.prepare(ctx_id=0, det_size=(640, 640))

        if not INSWAPPER_PATH.exists():
            raise FileNotFoundError(
                f"inswapper_128.onnx not found at {INSWAPPER_PATH}. "
                "Download from: huggingface.co/deepinsight/inswapper"
            )

        self.swapper = insightface.model_zoo.get_model(
            str(INSWAPPER_PATH),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )

        try:
            from gfpgan import GFPGANer

            self.enhancer = GFPGANer(
                model_path="./models/gfpgan/GFPGANv1.4.pth",
                upscale=1,
                arch="clean",
                channel_multiplier=2,
                bg_upsampler=None,
            )
            logger.info("GFPGAN enhancer loaded")
        except ImportError:
            logger.warning("GFPGAN not installed - running without enhancement")
            self.enhancer = None

        logger.info("FaceSwapEngine loaded successfully")

    def set_target_face(self, image_bytes: bytes) -> bool:
        """
        Extract face from reference image bytes and set as swap target.
        image_bytes: raw JPEG or PNG bytes - never written to disk.
        Returns True if face detected, False if no face found.
        Raises ValueError if image cannot be decoded.
        """
        if self.face_analyzer is None:
            logger.warning("FaceSwapEngine not loaded - cannot set target face")
            return False

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image - invalid or corrupt file")

        faces = self.face_analyzer.get(img)
        if not faces:
            logger.warning("No face detected in reference image")
            return False

        target = max(
            faces,
            key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
        )
        with self._lock:
            self._target_face = target
        logger.info("Target face set from reference image")
        return True

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Swap all faces in a webcam frame with the target face.
        frame: BGR numpy array from cv2.VideoCapture
        Returns BGR numpy array with faces swapped.
        Returns original frame if no target set or no face detected.
        No frames are saved to disk at any point.
        """
        with self._lock:
            if self._target_face is None:
                return frame

        if self.face_analyzer is None:
            logger.warning("FaceSwapEngine not loaded - returning original frame")
            return frame

        faces = self.face_analyzer.get(frame)
        if not faces:
            return frame

        result = frame.copy()
        for face in faces:
            result = self._run_swap(result, face)

        if self.enhancer is not None:
            result = self._run_enhance(result)

        return result

    def _run_swap(self, frame: np.ndarray, source_face: Any) -> np.ndarray:
        """Run inswapper_128 swap for a single detected face."""
        try:
            with self._lock:
                target = self._target_face
            if target is None or self.swapper is None:
                return frame
            return self.swapper.get(frame, source_face, target, paste_back=True)
        except Exception as exc:
            logger.error("Face swap failed for frame: %s", exc)
            return frame

    def set_target_from_embedding(self, embedding: np.ndarray) -> None:
        """
        Set swap target directly from a saved embedding vector.

        Args:
            embedding: InsightFace embedding array to activate.
        """
        if insightface is None:
            raise RuntimeError("insightface not installed")

        face = insightface.app.common.Face(embedding=np.asarray(embedding))
        with self._lock:
            self._target_face = face
        logger.info("Target face set from stored embedding")

    def _run_enhance(self, frame: np.ndarray) -> np.ndarray:
        """Apply GFPGAN face restoration and enhancement."""
        try:
            _, _, enhanced = self.enhancer.enhance(
                frame,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
            )
            return enhanced if enhanced is not None else frame
        except Exception as exc:
            logger.error("GFPGAN enhancement failed: %s", exc)
            return frame

    def clear_target(self) -> None:
        """Clear target face from memory. Call on session end."""
        with self._lock:
            self._target_face = None
        logger.info("Target face cleared from memory")

    def get_target_embedding(self) -> np.ndarray | None:
        """
        Thread-safe read of current target embedding.
        Returns numpy array copy or None if no target set.
        Use this instead of reading _target_face directly.
        """
        with self._lock:
            if self._target_face is None:
                return None
            return self._target_face.embedding.copy()

    def unload(self) -> None:
        """Release all models and GPU memory. Call on app shutdown."""
        self.clear_target()
        self.face_analyzer = None
        self.swapper = None
        self.enhancer = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        logger.info("FaceSwapEngine unloaded - GPU memory released")
