from __future__ import annotations

from ..types import ImageData
from .base import ModalityAdapter, issue


class XrayAdapter(ModalityAdapter):
    modality, label = "xray", "X-ray"
    allowed = ("rotate", "translate", "scale", "flip", "elastic", "brightness_contrast", "gamma",
               "gaussian_noise", "gaussian_blur", "random_erasing")
    default_enabled = ("rotate", "translate", "scale", "brightness_contrast", "gamma", "gaussian_noise", "gaussian_blur")
    param_defaults = {"gaussian_noise": {"max_sigma": 0.05}, "elastic": {"max_displacement": 4.0, "smoothness": 12.0}}
    limits = {
        "rotate": {"max_degrees": (0, 15)}, "translate": {"max_fraction": (0, 0.10)}, "scale": {"range": (0.85, 1.15)},
        "elastic": {"max_displacement": (0, 8), "smoothness": (4, 30)},
        "brightness_contrast": {"brightness": (0, 0.2), "contrast": (0, 0.3)}, "gamma": {"gamma_range": (0.7, 1.4)},
        "gaussian_noise": {"max_sigma": (0, 0.15)}, "gaussian_blur": {"max_sigma": (0, 1.5)}, "random_erasing": {"max_area": (0, 0.05)},
    }
    policy_notes = ("Only the left-right flip exists and it needs explicit opt-in (laterality matters).",
                    "Rotation ≤ 15°, translation ≤ 10%, zoom 0.85–1.15 keep anatomy plausible.")

    def _modality_checks(self, img: ImageData) -> list[dict]:
        out = []
        if img.spatial_ndim != 2 or img.has_channels:
            out.append(issue("error", "dimension_mismatch", f"X-ray expects a single 2D image, found shape {img.array.shape}"))
        elif min(img.array.shape) < 32:
            out.append(issue("warning", "tiny_image", f"Image is very small ({img.array.shape})"))
        return out
