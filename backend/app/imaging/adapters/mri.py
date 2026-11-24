from __future__ import annotations

from ..types import ImageData
from .base import ModalityAdapter, issue


class MRIAdapter(ModalityAdapter):
    modality, label = "mri", "MRI"
    allowed = ("rotate", "translate", "scale", "flip", "elastic", "gamma", "intensity_scale", "bias_field",
               "gaussian_noise", "gaussian_blur", "random_erasing")
    default_enabled = ("rotate", "translate", "scale", "intensity_scale", "gamma", "bias_field", "gaussian_noise")
    param_defaults = {"gaussian_noise": {"max_sigma": 0.03}, "rotate": {"max_degrees": 6.0}}
    limits = {
        "rotate": {"max_degrees": (0, 10)}, "translate": {"max_fraction": (0, 0.08)}, "scale": {"range": (0.9, 1.1)},
        "elastic": {"max_displacement": (0, 4), "smoothness": (4, 30)}, "gamma": {"gamma_range": (0.8, 1.25)},
        "intensity_scale": {"max_scale_delta": (0, 0.2)}, "bias_field": {"strength": (0, 0.25)},
        "gaussian_noise": {"max_sigma": (0, 0.1)}, "gaussian_blur": {"max_sigma": (0, 1.2)}, "random_erasing": {"max_area": (0, 0.03)},
    }
    blocked_reason = {
        "brightness_contrast": "use the sequence-aware intensity_scale / gamma / bias_field transforms",
        "hu_shift": "Hounsfield Units exist only for CT",
    }
    policy_notes = ("Every sequence receives the identical spatial transform (and so does any mask); intensity changes are sampled per sequence.",
                    "Noise is Rician for non-negative magnitude images.")

    def _modality_checks(self, img: ImageData) -> list[dict]:
        if img.spatial_ndim != 3:
            return [issue("error", "dimension_mismatch", f"MRI expects a 3D volume (or aligned sequences), found shape {img.array.shape}")]
        return []
