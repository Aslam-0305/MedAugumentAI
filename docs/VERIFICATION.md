# Verification status

Built in a sandbox with **no network access**: FastAPI, Pydantic, nibabel, pydicom, pymongo, pytest and all npm packages were unavailable. The code is layered so that the core does not depend on them.

## Executed and passing (backend core, 23 tests)
Run with `python -m tests.run_without_pytest` (same functions run under pytest):
* PNG (8/16-bit) and NIfTI round trips (gz/plain, 3D/4D, affine, dtype); misaligned multi-sequence rejected
* Rotation is applied in physical space (sphere volume preserved with 1×1×3 mm voxels); image and mask share the same resampling
* Same seed ⇒ identical arrays; source arrays never mutated
* Modality policy (blocked transforms, flip opt-in, parameter clamping) and output validator (NaN, blank, no-change)
* Balancing: reproduces the design's worked example, caps, per-class cap, exclusions, custom targets, determinism, multilabel co-occurrence
* Ingestion: label↔image mapping, folder layout, missing/corrupt/duplicate/unlabelled rows, modality mismatch, zip-slip and path traversal, loose-file upload, multilabel detection, pseudonymisation
* Patient-level split with no leakage; leaky supplied splits rejected
* End-to-end for **X-ray, CT and MRI**: plan → job → provenance → export; originals unchanged by hash; lineage and train-only sources; geometry and masks preserved; export reloads with matching SHA-256; held-out splits byte-identical to originals; no raw patient IDs or upload filenames in the export; cancel; manual rejection
* Mutation checks: disabling the zip-slip guard or breaking patient grouping makes tests fail.

## Written but NOT executed here — please run
1. **FastAPI layer** (`app/api`, `app/main.py`, `schemas/requests.py`): compiled only. Start the server and open `/docs`; try upload → plan → job → export. Likeliest problem areas: multipart handling and Pydantic validation messages.
2. **MongoDB store** (`MongoStore`): the file store has identical semantics and is what tests use. Run the same workflow once with `DB_BACKEND=mongo`.
3. **DICOM loaders** (`loaders/dicom_loader.py`): never run (no pydicom, no DICOM samples). Test with a real series; check orientation/affine, MONOCHROME1 handling and compressed transfer syntaxes (may need `pylibjpeg`/`gdcm`).
4. **nibabel path**: only the built-in NIfTI fallback was exercised.
5. **Frontend**: not built or run. Statically checked only (bracket/JSX-tag balance, imports resolve and are exported, hooks imported; the checker was validated against a deliberately broken file). Run `npm install && npm run dev` and `npm test`; expect to fix small runtime or styling issues.
6. Performance on large datasets and the 4 GB upload path.
