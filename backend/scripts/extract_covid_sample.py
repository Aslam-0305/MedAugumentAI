"""Rebuild covid19_sample.zip with masks resized to match their images."""
import zipfile
import io
import os
import csv
from pathlib import Path
from PIL import Image

src_zip = Path(r"c:\Users\kalya\Downloads\medaugment-ai\COVID-19_Radiography_Dataset.zip")
out_zip = Path(r"c:\Users\kalya\Downloads\medaugment-ai\sample_data\covid19_sample.zip")
out_zip.parent.mkdir(parents=True, exist_ok=True)

samples_per_class = {
    "Normal": 50,
    "Lung_Opacity": 30,
    "COVID": 25,
    "Viral Pneumonia": 15,
}

manifest_rows = []

with zipfile.ZipFile(src_zip, "r") as zin, zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
    all_names = set(zin.namelist())
    for c, count in samples_per_class.items():
        prefix = f"COVID-19_Radiography_Dataset/{c}/images/"
        mask_prefix = f"COVID-19_Radiography_Dataset/{c}/masks/"

        img_names = [n for n in zin.namelist() if n.startswith(prefix) and n.endswith(".png")][:count]
        for img_name in img_names:
            base_filename = os.path.basename(img_name)
            name_stem = os.path.splitext(base_filename)[0]
            mask_name = f"{mask_prefix}{base_filename}"

            safe_class = c.replace(" ", "_")
            dest_img = f"images/{safe_class}_{base_filename}"
            dest_mask = f"masks/{safe_class}_{base_filename}"

            # Read image to get its dimensions
            img_data = zin.read(img_name)
            img_pil = Image.open(io.BytesIO(img_data))
            img_size = img_pil.size  # (width, height)

            zout.writestr(dest_img, img_data)

            has_mask = mask_name in all_names
            if has_mask:
                mask_data = zin.read(mask_name)
                mask_pil = Image.open(io.BytesIO(mask_data))
                # Resize mask to match image dimensions if they differ
                if mask_pil.size != img_size:
                    mask_pil = mask_pil.resize(img_size, Image.NEAREST)
                buf = io.BytesIO()
                mask_pil.save(buf, format="PNG")
                zout.writestr(dest_mask, buf.getvalue())
            
            manifest_rows.append({
                "image_path": dest_img,
                "patient_id": f"patient_{safe_class}_{name_stem}",
                "label": c,
                "mask_path": dest_mask if has_mask else ""
            })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["image_path", "patient_id", "label", "mask_path"])
    writer.writeheader()
    writer.writerows(manifest_rows)
    zout.writestr("manifest.csv", buf.getvalue().encode("utf-8"))

size_mb = out_zip.stat().st_size / (1024 * 1024)
print(f"Created {out_zip} with {len(manifest_rows)} images ({size_mb:.1f} MB)")
print("Masks have been resized to match image dimensions.")
