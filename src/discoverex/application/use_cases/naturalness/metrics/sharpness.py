from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def laplacian_variance(image: Image.Image) -> float:
    gray = np.asarray(image.convert("L"), dtype=np.uint8)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())
