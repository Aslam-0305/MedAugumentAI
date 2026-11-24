"""Privacy helpers: pseudonymisation and an allow-list of safe metadata."""
from __future__ import annotations

import hashlib
import hmac

# Only these DICOM attributes ever leave the loader. Everything else (names, IDs,
# dates, institutions, UIDs...) is dropped, never stored, logged or exported.
SAFE_DICOM_FIELDS = (
    "Modality", "ViewPosition", "ImageLaterality", "PhotometricInterpretation",
    "BitsStored", "SliceThickness", "RescaleSlope", "RescaleIntercept", "BodyPartExamined",
)

# Direct identifiers we look for so we can warn the user (names only, never values).
PHI_TAGS = (
    "PatientName", "PatientID", "PatientBirthDate", "PatientAddress", "OtherPatientIDs",
    "PatientTelephoneNumbers", "InstitutionName", "ReferringPhysicianName", "AccessionNumber",
)


def pseudonymize(salt: str, raw: str) -> str:
    """Stable keyed hash of a subject identifier; the raw value is never persisted."""
    digest = hmac.new(salt.encode(), raw.strip().encode(), hashlib.sha256).hexdigest()
    return f"S{digest[:12]}"
