from __future__ import annotations

from ..types import ImageData
from .base import ModalityAdapter, issue


class CTAdapter(ModalityAdapter):
    modality, label = "ct", "CT"
    allowed = ("rotate", "translate", "scale", "flip", "elastic", "hu_shift", "gaussian_noise", "gaussian_blur", "random_erasing")
    default_enabled = ("rotate", "translate", "scale", "hu_shift", "gaussian_noise", "gaussian_blur")
    param_defaults = {"gaussian_noise": {"max_sigma": 10.0}, "rotate": {"max_degrees": 6.0}}
    limits = {
        "rotate": {"max_degrees": (0, 10)}, "translate": {"max_fraction": (0, 0.08)}, "scale": {"range": (0.9, 1.1)},
        "elastic": {"max_displacement": (0, 4), "smoothness": (4, 30)}, "hu_shift": {"max_shift_hu": (0, 30)},
        "gaussian_noise": {"max_sigma": (0, 25)}, "gaussian_blur": {"max_sigma": (0, 1.2)}, "random_erasing": {"max_area": (0, 0.03)},
    }
    blocked_reason = {
        "gamma": "gamma/contrast curves would destroy calibrated Hounsfield Unit values (use hu_shift instead)",
        "brightness_contrast": "display-style brightness/contrast would destroy calibrated Hounsfield Unit values (use hu_shift instead)",
        "intensity_scale": "multiplicative scaling is for arbitrary-unit MRI intensities, not calibrated HU",
        "bias_field": "bias fields model MRI coil sensitivity",
    }
    policy_notes = ("Spatial transforms are applied to the whole 3D volume in physical space using voxel spacing.",
                    "Padding defaults to air (the volume minimum). Noise and shifts are expressed in HU.")

    def _modality_checks(self, img: ImageData) -> list[dict]:
        out = []
        if img.spatial_ndim != 3 or img.has_channels:
            out.append(issue("error", "dimension_mismatch", f"CT expects a single 3D volume, found shape {img.array.shape}"))
            return out
        lo, hi = float(img.array.min()), float(img.array.max())
        if lo > -200:  # real CT contains air (~ -1000 HU); a signed-HU volume without it is likely normalised or shifted
            out.append(issue("warning", "not_hounsfield", f"Intensity range {lo:.0f}…{hi:.0f} does not look like Hounsfield Units; HU-based settings may be inappropriate"))
        return out
