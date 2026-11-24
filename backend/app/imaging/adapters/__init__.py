from __future__ import annotations

from ...utils.common import AppError
from .base import ModalityAdapter
from .ct import CTAdapter
from .mri import MRIAdapter
from .xray import XrayAdapter

_ADAPTERS: dict[str, ModalityAdapter] = {"xray": XrayAdapter(), "ct": CTAdapter(), "mri": MRIAdapter()}


def get_adapter(modality: str) -> ModalityAdapter:
    try:
        return _ADAPTERS[modality]
    except KeyError:
        raise AppError(f"Unsupported modality '{modality}'. Use one of: xray, ct, mri", 400, "unsupported_modality") from None
