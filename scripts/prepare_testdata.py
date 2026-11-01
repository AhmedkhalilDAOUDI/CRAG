"""Sample a small, reproducible test corpus from the Kaggle resume dataset.

Test data only: these files validate the pipeline and are never part of the
report. Two PDFs are also rendered to PNG to exercise the OCR path.
"""
import random
import shutil
import sys
from pathlib import Path

import pypdfium2

SRC = Path.home() / ".cache/kagglehub/datasets/snehaanbhawal/resume-dataset/versions/1/data/data"
DST = Path(__file__).resolve().parent.parent / "data" / "testdocs"
CATEGORIES = ["INFORMATION-TECHNOLOGY", "ENGINEERING", "FINANCE", "HR", "CONSTRUCTION", "HEALTHCARE"]
PER_CATEGORY = 6


def main() -> None:
    if not SRC.exists():
        sys.exit(f"Dataset not found at {SRC}. Run: kagglehub.dataset_download('snehaanbhawal/resume-dataset')")
    rng = random.Random(42)
    DST.mkdir(parents=True, exist_ok=True)
    picked = []
    for cat in CATEGORIES:
        files = sorted((SRC / cat).glob("*.pdf"))
        for f in rng.sample(files, PER_CATEGORY):
            out = DST / f"{cat}__{f.name}"
            shutil.copy(f, out)
            picked.append(out)
    # Scanned-document simulation: image-only copies force the OCR branch.
    for f in picked[:2]:
        page = pypdfium2.PdfDocument(f)[0]
        page.render(scale=2).to_pil().save(DST / f"SCANNED__{f.stem}.png")
    print(f"{len(picked)} PDFs + 2 scanned PNGs in {DST}")


if __name__ == "__main__":
    main()
