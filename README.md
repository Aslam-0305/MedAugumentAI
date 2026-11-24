# MedAugment AI

Medical-imaging dataset **augmentation and export** platform (React + FastAPI). Upload an X-ray, CT or MRI dataset with labels, see how imbalanced it is, plan a balancing target, generate additional **training** samples with conservative, **non-generative** transformations, review them side by side, and export a labelled dataset with full provenance.

> Research data-preparation tool, **not** a diagnostic system. Augmented images are transformed copies of existing images, not new patients or independent clinical observations. Technical checks cannot prove clinical validity; review samples before use.

Implements `MedAugment_AI_Project_Design_Document.docx` v1.0 (see [Deviations](#deviations-from-the-design-document) for the few places it differs).

## Quick start

**Backend** (Python 3.11+)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set DB_BACKEND=file to run without MongoDB
uvicorn app.main:app --reload   # API on :8000, Swagger UI at /docs
```
MongoDB: `docker compose up mongo` (or `docker compose up` for mongo + backend).

**Frontend** (Node 18+)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173 (proxies /api to :8000)
```

**Try it with synthetic data** (procedurally drawn shapes, not patient data):
```bash
cd backend
python -m scripts.make_sample_data --modality xray --out ../sample_data     # also: ct, mri, --multilabel
```
Upload `sample_data/xray_sample.zip` (it contains `manifest.csv`). The CT/MRI samples include masks.

## Workflow
1. **Upload** a ZIP (+ optional CSV) and choose the modality. Content is validated (decodes, dimensions, labels, duplicates, mask alignment); invalid images are listed and excluded.
2. **Explore** class counts, imbalance ratio, multilabel co-occurrence, previews.
3. **Split** patient-level into train/val/test (seeded) or adopt the manifest's splits. Only train is ever augmented.
4. **Plan**: choose a balancing strategy, caps and transforms, preview examples, review the projected distribution and warnings.
5. **Generate** in a background job (progress, logs, cancel). Every output is technically checked; rejected outputs are retried with a fresh random draw and never written.
6. **Review** original-vs-augmented, provenance, accept/reject samples.
7. **Export** a ZIP: images, masks, `manifest.csv/json` (labels, lineage, transform history, SHA-256), `provenance.jsonl`, `config.json`, `summary_report.json/.md`.

### Manifest format
```csv
image_path,patient_id,label            # single-label
image_path,patient_id,normal,pneumonia # multilabel: one 0/1 column per class
image_path,patient_id,labels           # multilabel: "pneumonia|effusion"
```
Optional columns: `split` (train/val/test), `mask_path`. MRI sequences: several paths in `image_path` separated by `;`, or one 4D NIfTI. Folder layout: `Class/image files` (single-label only).

## Design decisions worth knowing
* **Modality policy is enforced, not advisory.** e.g. gamma/contrast curves are rejected for CT (they destroy HU), HU shifts only exist for CT, left-right flips need an explicit opt-in, parameters are clamped to per-modality limits with a warning.
* **Physical-space geometry.** Rotation/scale use voxel spacing, so anisotropic CT/MRI voxels are not sheared. All spatial transforms of a sample are composed into **one** resampling; the same mapping goes to the image (chosen interpolation) and the mask (nearest). MRI sequences share the spatial transform; intensity is sampled per sequence.
* **Reproducibility.** Each variant's RNG derives from `(job seed, source id, variant, attempt)` via SHA-256, independent of scheduling order. Same seed + settings ⇒ byte-identical outputs (tested).
* **Originals are immutable** (verified by hash in tests); augmented files live under `storage/augmented/{job_id}`.
* **Privacy.** Subject IDs are HMAC-pseudonymised on ingest (raw IDs never stored); only an allow-list of DICOM fields is read, PHI tags are detected (names only) and reported; exports use generated file names; DICOM inputs are exported as NIfTI/PNG without DICOM metadata; ZIPs are guarded against zip-slip, symlinks, bombs and size limits. Optional `API_KEY` header auth exists — add real authN/Z before any multi-user deployment.
* **Multilabel** planning is a greedy, documented heuristic that accounts for co-occurrence; it reports overshoot instead of promising equal counts.

## API
Swagger at `/docs`. Main routes under `/api/v1`: `POST/GET /datasets`, `GET /datasets/{id}/statistics`, `GET /datasets/{id}/images`, `POST /datasets/{id}/splits`, `GET /augmentation/transforms`, `POST /augmentation/plan`, `POST /augmentation/jobs`, `POST /augmentation/preview`, `GET /jobs/{id}`, `POST /jobs/{id}/cancel`, `GET /jobs/{id}/results`, `PATCH /jobs/{id}/samples/{sid}`, `GET /images/{id}/preview`, `POST /exports`, `GET /exports/{id}[/download]`.

## Tests
```bash
cd backend && pytest                 # or: python -m tests.run_without_pytest
cd frontend && npm test
```
See [docs/VERIFICATION.md](docs/VERIFICATION.md) for exactly what has and has not been executed.

## Deviations from the design document
| Design | Here | Why |
|---|---|---|
| MONAI + Albumentations | NumPy/SciPy/OpenCV transform engine | One n-D implementation with physical-space geometry and mask consistency, no PyTorch dependency. The `transforms/` package is the seam to swap MONAI in. |
| `geometric_2d/intensity_2d/spatial_3d/intensity_3d.py` | `transforms/spatial.py`, `intensity.py`, `registry.py` | Same code serves 2D and 3D, so splitting by dimensionality would duplicate it. |
| Celery + Redis "later" | Thread-pool worker behind a plain function `run_augmentation_job(ctx, job_id)` | Allowed for prototypes by §11.1; not durable (jobs interrupted by a restart are marked failed). Wrap the function in a Celery task to scale. |
| MixUp / CutMix | Not implemented | Need soft labels, which the hard-label export/manifest doesn't model. |
| On-the-fly augmentation | Rejected with a clear error | Only materialised output is supported. |
| Separate balancing and augmentation pages | One "Plan augmentation" page | The plan depends on both; fewer round trips. |
| DICOM export preserve/sanitise | Always sanitise (convert to NIfTI/PNG) | Safest default; writing DICOM is out of scope. |

## Known limitations
* **DICOM loading is untested** (see VERIFICATION.md). NIfTI uses nibabel when installed, otherwise a built-in NIfTI-1 reader/writer (no NIfTI-2).
* Ingestion loads each image fully to validate it: fine for thousands of 2D images or tens of volumes, slow for very large CT/MRI collections. Elastic deformation of big volumes builds full coordinate grids (memory-hungry).
* `DB_BACKEND=file` rewrites a JSON file and is for trials only; use MongoDB for real use.
* Rows with no positive label are treated as *missing labels* and excluded — add an explicit "normal" column for no-finding cases.
* Class counts in a multilabel plan are label occurrences; they will not be equal.

## Layout
```
backend/app/{api,schemas,services,imaging/{loaders,adapters,transforms},workers,utils}  backend/tests  backend/scripts
frontend/src/{api,components,features,pages,layouts}      storage/   docs/   docker-compose.yml
```
