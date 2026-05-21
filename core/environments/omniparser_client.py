"""OmniParser v2 client for AgentOS vision escalation.

This module wraps Microsoft's OmniParser v2 to provide structured UI element
detection from screenshots. It is the final escalation layer after:
1. UIA accessibility tree (primary)
2. OpenCV heuristics (first fallback)
3. OmniParser v2 (second fallback — for Electron, dark UIs, custom apps)

Models are downloaded lazily from HuggingFace on first use.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Heavy imports are deferred to _load_models() to avoid startup overhead
try:
    import numpy as np
except Exception:
    np = None  # type: ignore

try:
    import cv2
except Exception:
    cv2 = None  # type: ignore


# ------------------------------------------------------------------
# Coordinate / box helpers (inlined from OmniParser util)
# ------------------------------------------------------------------

def _box_area(box: List[float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _intersection_area(box1: List[float], box2: List[float]) -> float:
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def _iou(box1: List[float], box2: List[float]) -> float:
    inter = _intersection_area(box1, box2)
    union = _box_area(box1) + _box_area(box2) - inter + 1e-6
    if _box_area(box1) > 0 and _box_area(box2) > 0:
        ratio1 = inter / _box_area(box1)
        ratio2 = inter / _box_area(box2)
    else:
        ratio1, ratio2 = 0.0, 0.0
    return max(inter / union, ratio1, ratio2)


def _is_inside(box1: List[float], box2: List[float]) -> bool:
    """Return True if box1 is mostly inside box2 (>80% overlap)."""
    inter = _intersection_area(box1, box2)
    ratio = inter / (_box_area(box1) + 1e-6)
    return ratio > 0.80


def _remove_overlap_new(
    icon_boxes: List[Dict[str, Any]],
    ocr_boxes: List[Dict[str, Any]],
    iou_threshold: float = 0.7,
) -> List[Dict[str, Any]]:
    """Merge OCR text boxes with YOLO icon boxes, removing overlaps.

    Inlined and simplified from OmniParser util/utils.py.
    """
    filtered = list(ocr_boxes)

    for icon in icon_boxes:
        box1 = icon["bbox"]
        # Skip if icon overlaps with a larger icon
        is_valid = True
        for other in icon_boxes:
            if other is icon:
                continue
            box2 = other["bbox"]
            if _iou(box1, box2) > iou_threshold and _box_area(box1) > _box_area(box2):
                is_valid = False
                break
        if not is_valid:
            continue

        # Check overlap with OCR boxes
        box_added = False
        ocr_labels = ""
        for ocr in list(filtered):
            box3 = ocr["bbox"]
            if _is_inside(box3, box1):
                # OCR inside icon: merge label into icon
                try:
                    ocr_labels += ocr.get("content", "") + " "
                    filtered.remove(ocr)
                except Exception:
                    continue
            elif _is_inside(box1, box3):
                # Icon inside OCR: skip this icon
                box_added = True
                break

        if not box_added:
            content = (ocr_labels.strip() or None) if ocr_labels else None
            filtered.append({
                "type": "icon",
                "bbox": box1,
                "interactivity": True,
                "content": content,
            })

    return filtered


# ------------------------------------------------------------------
# OmniParser client
# ------------------------------------------------------------------

class OmniParserClient:
    """Self-contained OmniParser v2 inference client.

    Downloads model weights from HuggingFace on first use.
    Runs entirely on CPU if no CUDA is available.
    """

    _instance: Optional["OmniParserClient"] = None
    _models_loaded = False

    HF_REPO = "microsoft/OmniParser-v2.0"
    BOX_THRESHOLD = 0.01
    IOU_THRESHOLD = 0.7
    CAPTION_BATCH_SIZE = 16

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._yolo_model = None
        self._caption_processor = None
        self._caption_model = None
        self._easyocr_reader = None
        self._weights_dir: Optional[str] = None
        self._device = "cpu"

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if all heavy dependencies are importable."""
        try:
            import torch  # noqa: F401
            from PIL import Image  # noqa: F401
            from transformers import AutoProcessor, AutoModelForCausalLM  # noqa: F401
            from ultralytics import YOLO  # noqa: F401
            import easyocr  # noqa: F401
            return True
        except Exception as e:
            logger.debug(f"OmniParser dependencies missing: {e}")
            return False

    def _get_local_weights_dir(self) -> Optional[str]:
        """Check for pre-downloaded weights in repo-local directory."""
        # Check relative to this file: ../../weights/omniparser
        here = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(here, "..", "..", "weights", "omniparser")
        candidate = os.path.normpath(candidate)
        yolo_path = os.path.join(candidate, "icon_detect", "model.pt")
        caption_path = os.path.join(candidate, "icon_caption")
        if os.path.exists(yolo_path) and os.path.exists(caption_path):
            return candidate
        return None

    def _download_weights(self) -> str:
        """Download model weights from HuggingFace. Returns local cache path."""
        from huggingface_hub import snapshot_download
        logger.info("OmniParser: downloading model weights (first use, ~1GB)...")
        t0 = time.time()
        local_dir = snapshot_download(
            repo_id=self.HF_REPO,
            repo_type="model",
            allow_patterns=["icon_detect/*", "icon_caption/*"],
        )
        logger.info(f"OmniParser: weights downloaded to {local_dir} in {time.time()-t0:.1f}s")
        return local_dir

    def _load_models(self) -> bool:
        """Lazy-load YOLO + Florence-2 + EasyOCR. Returns True on success."""
        if self._models_loaded:
            return True
        if not self.is_available():
            logger.warning("OmniParser: dependencies not available")
            return False

        try:
            import torch
            from ultralytics import YOLO
            from transformers import AutoProcessor, AutoModelForCausalLM
            import easyocr

            self._device = "cuda" if torch.cuda.is_available() else "cpu"

            # 1. Locate weights (local first, then download)
            if self._weights_dir is None:
                local = self._get_local_weights_dir()
                if local:
                    logger.info(f"OmniParser: using local weights at {local}")
                    self._weights_dir = local
                else:
                    self._weights_dir = self._download_weights()

            # 2. Load YOLO icon detector
            yolo_path = os.path.join(self._weights_dir, "icon_detect", "model.pt")
            if not os.path.exists(yolo_path):
                raise FileNotFoundError(f"YOLO model not found: {yolo_path}")
            logger.info(f"OmniParser: loading YOLO from {yolo_path}")
            self._yolo_model = YOLO(yolo_path)

            # 3. Load Florence-2 captioner
            caption_path = os.path.join(self._weights_dir, "icon_caption")
            if not os.path.exists(caption_path):
                raise FileNotFoundError(f"Caption model not found: {caption_path}")
            logger.info(f"OmniParser: loading Florence-2 from {caption_path}")
            self._caption_processor = AutoProcessor.from_pretrained(
                "microsoft/Florence-2-base",
                trust_remote_code=True,
            )
            dtype = torch.float16 if self._device == "cuda" else torch.float32
            self._caption_model = AutoModelForCausalLM.from_pretrained(
                caption_path,
                torch_dtype=dtype,
                trust_remote_code=True,
            ).to(self._device)

            # 4. Init EasyOCR (downloads ~100MB English model on first use)
            logger.info("OmniParser: initializing EasyOCR...")
            self._easyocr_reader = easyocr.Reader(["en"], gpu=(self._device == "cuda"))

            self._models_loaded = True
            logger.info("OmniParser: all models loaded successfully")
            return True

        except Exception as e:
            logger.error(f"OmniParser: model loading failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def parse_image(self, image_source: Any) -> List[Dict[str, Any]]:
        """Run full OmniParser pipeline on a PIL Image or image path.

        Returns a list of element dicts:
            {
                "type": "text" | "icon",
                "bbox": [x1, y1, x2, y2],  # pixel coordinates
                "interactivity": bool,
                "content": str | None,
            }
        """
        if not self._load_models():
            return []

        from PIL import Image

        t0 = time.time()

        # Normalize input to PIL Image
        if isinstance(image_source, str):
            pil_img = Image.open(image_source).convert("RGB")
        elif isinstance(image_source, Image.Image):
            pil_img = image_source.convert("RGB")
        else:
            # Assume numpy array
            pil_img = Image.fromarray(image_source).convert("RGB")

        w, h = pil_img.size
        image_np = np.array(pil_img)

        # 1. OCR -------------------------------------------------------
        ocr_result = self._easyocr_reader.readtext(image_np, text_threshold=0.8)
        ocr_text = [r[1] for r in ocr_result]
        ocr_bbox = [self._easyocr_to_xyxy(r[0]) for r in ocr_result]

        # 2. YOLO icon detection ---------------------------------------
        yolo_result = self._yolo_model.predict(
            source=pil_img,
            conf=self.BOX_THRESHOLD,
            imgsz=(h, w),
            iou=0.1,
            verbose=False,
        )
        yolo_boxes = yolo_result[0].boxes.xyxy  # pixel space

        # 3. Merge OCR + icon boxes ------------------------------------
        ocr_elems = [
            {"type": "text", "bbox": b, "interactivity": False, "content": t}
            for b, t in zip(ocr_bbox, ocr_text)
        ]
        icon_elems = [
            {"type": "icon", "bbox": b.tolist(), "interactivity": True, "content": None}
            for b in yolo_boxes
        ]
        filtered = _remove_overlap_new(icon_elems, ocr_elems, iou_threshold=self.IOU_THRESHOLD)

        # 4. Caption icons ---------------------------------------------
        starting_idx = next(
            (i for i, box in enumerate(filtered) if box.get("content") is None), -1
        )
        if starting_idx >= 0:
            icon_boxes = filtered[starting_idx:]
            captions = self._caption_icons(icon_boxes, image_np, batch_size=self.CAPTION_BATCH_SIZE)
            for box, cap in zip(icon_boxes, captions):
                box["content"] = cap

        logger.info(
            f"OmniParser: parsed {len(filtered)} elements in {time.time()-t0:.2f}s "
            f"({len(ocr_text)} OCR + {len(yolo_boxes)} icons)"
        )
        return filtered

    def _easyocr_to_xyxy(self, quad: List[List[float]]) -> List[int]:
        """Convert EasyOCR 4-point quad to xyxy bbox."""
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]

    def _caption_icons(
        self,
        icon_boxes: List[Dict[str, Any]],
        image_np: np.ndarray,
        batch_size: int = 16,
    ) -> List[str]:
        """Caption icon regions using Florence-2."""
        import torch
        from torchvision.transforms import ToPILImage

        to_pil = ToPILImage()
        crops = []
        for box in icon_boxes:
            x1, y1, x2, y2 = map(int, box["bbox"])
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(image_np.shape[1], x2), min(image_np.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                crops.append(Image.new("RGB", (64, 64), (128, 128, 128)))
                continue
            cropped = image_np[y1:y2, x1:x2, :]
            cropped = cv2.resize(cropped, (64, 64))
            crops.append(to_pil(cropped))

        model = self._caption_model
        processor = self._caption_processor
        device = model.device
        prompt = "<CAPTION>"
        generated_texts: List[str] = []

        for i in range(0, len(crops), batch_size):
            batch = crops[i : i + batch_size]
            try:
                if device.type == "cuda":
                    inputs = processor(
                        images=batch,
                        text=[prompt] * len(batch),
                        return_tensors="pt",
                        do_resize=False,
                    ).to(device=device, dtype=torch.float16)
                else:
                    inputs = processor(
                        images=batch,
                        text=[prompt] * len(batch),
                        return_tensors="pt",
                    ).to(device=device)

                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=20,
                    num_beams=1,
                    do_sample=False,
                )
                text = processor.batch_decode(generated_ids, skip_special_tokens=True)
                generated_texts.extend([t.strip() for t in text])
            except Exception as e:
                logger.warning(f"OmniParser caption batch failed: {e}")
                generated_texts.extend(["icon"] * len(batch))

        return generated_texts


# Singleton accessor
_omni_client: Optional[OmniParserClient] = None


def get_omni_parser() -> OmniParserClient:
    global _omni_client
    if _omni_client is None:
        _omni_client = OmniParserClient()
    return _omni_client
