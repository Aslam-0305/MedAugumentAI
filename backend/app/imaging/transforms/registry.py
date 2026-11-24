"""Catalogue of supported non-generative transforms (metadata only; no image code).

Exposed to the UI through GET /augmentation/transforms so the frontend builds its
controls from the same source of truth the backend enforces.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ALL = ("xray", "ct", "mri")


@dataclass(frozen=True)
class TransformInfo:
    name: str
    label: str
    family: str  # geometric | intensity | noise | deformation | occlusion
    kind: str  # spatial (resamples geometry; also applied to masks) | intensity
    description: str
    defaults: dict
    probability: float
    modalities: tuple[str, ...] = ALL
    caution: str | None = None
    param_help: dict = field(default_factory=dict)


REGISTRY: dict[str, TransformInfo] = {t.name: t for t in [
    TransformInfo("rotate", "Rotation", "geometric", "spatial",
                  "Small rotation about the image centre (about each enabled axis for volumes), applied in physical space.",
                  {"max_degrees": 8.0}, 0.7, param_help={"max_degrees": "Maximum angle in degrees (±)."}),
    TransformInfo("translate", "Translation", "geometric", "spatial", "Shift the content by a fraction of each dimension.",
                  {"max_fraction": 0.05}, 0.7, param_help={"max_fraction": "Maximum shift as a fraction of the extent (±)."}),
    TransformInfo("scale", "Scaling", "geometric", "spatial", "Isotropic zoom about the centre.",
                  {"range": [0.92, 1.08]}, 0.6, param_help={"range": "[min, max] zoom factor."}),
    TransformInfo("flip", "Left-right flip", "geometric", "spatial", "Mirror along the left-right axis.", {}, 0.5,
                  caution="Changes laterality (heart side, asymmetric findings). Blocked unless 'Allow laterality flips' is enabled."),
    TransformInfo("elastic", "Elastic deformation", "deformation", "spatial", "Smooth random displacement field.",
                  {"max_displacement": 3.0, "smoothness": 8.0}, 0.3,
                  caution="Can distort anatomy or lesion geometry. Keep conservative and review previews.",
                  param_help={"max_displacement": "Maximum displacement in physical units (mm, or pixels when spacing is unknown).",
                              "smoothness": "Smoothing in voxels; larger = gentler deformation."}),
    TransformInfo("brightness_contrast", "Brightness / contrast", "intensity", "intensity",
                  "Linear contrast change about the mean plus a brightness shift.",
                  {"brightness": 0.08, "contrast": 0.15}, 0.6, ("xray",),
                  param_help={"brightness": "Shift as a fraction of the intensity range (±).", "contrast": "Contrast change (±)."}),
    TransformInfo("gamma", "Gamma", "intensity", "intensity", "Non-linear intensity curve on min-max normalised values.",
                  {"gamma_range": [0.85, 1.2]}, 0.5, ("xray", "mri"), param_help={"gamma_range": "[min, max] gamma."}),
    TransformInfo("hu_shift", "HU shift", "intensity", "intensity",
                  "Additive shift in Hounsfield Units (simulates calibration/kVp variation). Raw HU semantics preserved.",
                  {"max_shift_hu": 15.0}, 0.5, ("ct",), param_help={"max_shift_hu": "Maximum shift in HU (±)."}),
    TransformInfo("intensity_scale", "Intensity scale", "intensity", "intensity",
                  "Multiplicative scale, sampled independently per MRI sequence (arbitrary units).",
                  {"max_scale_delta": 0.1}, 0.6, ("mri",), param_help={"max_scale_delta": "Scale factor is 1 ± this."}),
    TransformInfo("bias_field", "Bias field", "intensity", "intensity", "Smooth multiplicative inhomogeneity (coil sensitivity).",
                  {"strength": 0.1}, 0.4, ("mri",), param_help={"strength": "Peak deviation from 1."}),
    TransformInfo("gaussian_noise", "Noise", "noise", "intensity",
                  "Gaussian noise (Rician magnitude noise for MRI). X-ray/MRI: fraction of image std; CT: HU.",
                  {"max_sigma": 0.05}, 0.4, param_help={"max_sigma": "Upper bound of the sampled noise level."}),
    TransformInfo("gaussian_blur", "Blur", "noise", "intensity", "Slight blur simulating resolution variation.",
                  {"max_sigma": 0.8}, 0.25, param_help={"max_sigma": "Maximum sigma in voxels (isotropic in physical space)."}),
    TransformInfo("random_erasing", "Random erasing", "occlusion", "intensity",
                  "Replace one small patch with the image mean. Never overlaps annotated masks.",
                  {"max_area": 0.02}, 0.2,
                  caution="May hide diagnostically relevant regions when no mask is supplied. Off by default."),
]}

# Order in which intensity transforms are applied (noise last, as in real acquisition chains).
INTENSITY_ORDER = ("bias_field", "brightness_contrast", "gamma", "hu_shift", "intensity_scale", "gaussian_blur", "gaussian_noise", "random_erasing")
SPATIAL_NAMES = tuple(n for n, t in REGISTRY.items() if t.kind == "spatial")
