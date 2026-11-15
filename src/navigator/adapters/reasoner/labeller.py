import asyncio
import io
from collections.abc import AsyncIterator, Collection, Sequence

import cv2
import numpy as np
from fastforks import detection, segmentation
from fastforks import promptable_segmentation as masking
from PIL import Image

from navigator.domain.guidance import GuidanceInstruction, GuidanceRequest
from navigator.domain.tags import MAX_TAGS, Outline, SceneTag, clean_tags

STRUCTURE = ("wall", "door", "stairs", "stairway", "escalator")
OBJECTS = (
    "person",
    "chair",
    "couch",
    "bench",
    "dining table",
    "potted plant",
    "bicycle",
    "motorcycle",
    "car",
    "bus",
    "truck",
    "traffic light",
    "stop sign",
    "fire hydrant",
    "dog",
    "suitcase",
)
APPEAR_AREA, STAY_AREA = 0.03, 0.015
OBJECT_SCORE = 0.5
OBJECT_AREA = 0.01
OUTLINE_TOLERANCE_PX = 2.0
_SMOOTHING = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def outline(mask: np.ndarray) -> Outline:
    height, width = mask.shape
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return ()
    largest = max(contours, key=cv2.contourArea)
    points = cv2.approxPolyDP(largest, OUTLINE_TOLERANCE_PX, True).reshape(-1, 2)
    if len(points) < 3:
        return ()
    return tuple(
        (round(float(x) / width, 3), round(float(y) / height, 3)) for x, y in points
    )


def smoothed(mask: np.ndarray) -> np.ndarray:
    opened = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, _SMOOTHING)
    return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, _SMOOTHING)


def structure_tags(
    labels: np.ndarray, class_names: Sequence[str], seen: Collection[str] = ()
) -> list[SceneTag]:
    tags = []
    for index, name in enumerate(class_names):
        if name.strip() not in STRUCTURE:
            continue
        mask = labels == index
        if mask.mean() >= (STAY_AREA if name in seen else APPEAR_AREA):
            tags.append(SceneTag(name, outline(smoothed(mask))))
    return tags


def coverage(box: Sequence[float], width: int, height: int) -> float:
    x0, y0, x1, y1 = (float(value) for value in box)
    if not np.isfinite([x0, y0, x1, y1]).all() or x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0) / (width * height)


def prominent(
    detections: Sequence[dict], width: int, height: int, limit: int
) -> list[dict]:
    return [
        d
        for d in detections
        if d["class_name"] in OBJECTS
        and d["score"] >= OBJECT_SCORE
        and coverage(d["box"], width, height) >= OBJECT_AREA
    ][:limit]


def confirmed(found: Sequence[SceneTag], seen: Collection[str]) -> list[SceneTag]:
    return [tag for tag in found if tag.label in seen]


class LabellerSceneReasoner:
    def __init__(self, detector: str, segmenter: str, masker: str) -> None:
        self._names = (detector, segmenter, masker)
        self._detector = None
        self._segmenter = None
        self._masker = None
        self._seen: frozenset[str] = frozenset()

    def __enter__(self) -> "LabellerSceneReasoner":
        detector, segmenter, masker = self._names
        self._detector = detection.load(detector)
        self._segmenter = segmentation.load(segmenter)
        self._masker = masking.load(masker)
        return self

    def __exit__(self, *exc) -> None:
        self._detector = None
        self._segmenter = None
        self._masker = None

    def _object_tags(self, picture: np.ndarray, limit: int) -> list[SceneTag]:
        height, width = picture.shape[:2]
        found = prominent(self._detector(picture).to_list(), width, height, limit)
        if not found:
            return []
        masks = self._masker(
            self._masker.get_image_embeddings(picture),
            input_boxes=[[float(v) for v in d["box"]] for d in found],
            multimask_output=False,
        ).masks[:, 0]
        return [
            SceneTag(d["class_name"], outline(mask))
            for d, mask in zip(found, masks.cpu().numpy())
        ]

    def _tags(self, jpeg: bytes) -> tuple[SceneTag, ...]:
        picture = np.asarray(Image.open(io.BytesIO(jpeg)).convert("RGB"))
        segments = self._segmenter(picture)
        structure = structure_tags(
            segments.labels.cpu().numpy(), segments.class_names, self._seen
        )
        objects = self._object_tags(picture, MAX_TAGS - len(structure))
        found = [tag for tag in structure + objects if tag.outline]
        shown = confirmed(found, self._seen)
        self._seen = frozenset(tag.label for tag in found)
        return clean_tags(shown)

    async def advise(
        self, request: GuidanceRequest
    ) -> AsyncIterator[GuidanceInstruction]:
        tags = await asyncio.to_thread(self._tags, request.camera_jpeg)
        if tags:
            yield GuidanceInstruction(
                phrase=None,
                text="",
                frame_id=request.geometry.frame_id,
                t_capture_ns=request.geometry.t_capture_ns,
                tags=tags,
            )
