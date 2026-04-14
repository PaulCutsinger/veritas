"""
veritas.impl.segmentation.sam_segmentor
----------------------------------------
Concrete Segmentor backed by Meta's Segment Anything Model (SAM).

This is a structured stub ready to be filled in once a SAM checkpoint is
available. Import-guard ensures the module loads cleanly even without the
`segment_anything` package installed.
"""
from __future__ import annotations

from pathlib import Path

try:
    from segment_anything import SamPredictor, sam_model_registry  # type: ignore
    _HAS_SAM = True
except ImportError:
    _HAS_SAM = False

from ...core.models import SegmentResult
from ...interface.segmentor import Segmentor


class SamSegmentor(Segmentor):
    """Segment an image using Meta's Segment Anything Model.

    Args:
        checkpoint: Path to the SAM model checkpoint (.pth file).
        model_type: SAM model type, e.g. ``"vit_h"``, ``"vit_l"``, ``"vit_b"``.
        device: Torch device string, e.g. ``"cuda"`` or ``"cpu"``.
    """

    def __init__(
        self,
        checkpoint: str | Path,
        model_type: str = "vit_h",
        device: str = "cuda",
    ) -> None:
        if not _HAS_SAM:
            raise ImportError(
                "Install segment-anything and provide a model checkpoint. "
                "See https://github.com/facebookresearch/segment-anything "
                "and download a checkpoint from the model zoo."
            )
        self._checkpoint = Path(checkpoint)
        self._model_type = model_type
        self._device = device
        self._predictor: "SamPredictor | None" = None

    def _load_model(self) -> "SamPredictor":
        if self._predictor is not None:
            return self._predictor
        if not self._checkpoint.exists():
            raise FileNotFoundError(
                f"SAM checkpoint not found: {self._checkpoint}. "
                "Download from https://github.com/facebookresearch/segment-anything"
            )
        sam = sam_model_registry[self._model_type](checkpoint=str(self._checkpoint))
        sam.to(device=self._device)
        self._predictor = SamPredictor(sam)
        return self._predictor

    def segment(self, image_path: str, labels: list[str] | None = None) -> SegmentResult:
        """Segment all objects in *image_path*, optionally filtering by *labels*.

        Args:
            image_path: Path to the rendered image (PNG/JPEG).
            labels: Optional list of semantic labels to target. If None, all
                    detectable segments are returned.

        Returns:
            SegmentResult with mask data and associated labels.
        """
        raise NotImplementedError(
            "Install segment-anything and provide a model checkpoint. "
            "Fill in this method body once SAM is configured — "
            "see veritas/impl/segmentation/sam_segmentor.py for the scaffold."
        )
