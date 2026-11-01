"""Ingest a folder of documents into the configured store.

  python scripts/ingest.py data/testdocs --profiles     # each file is one person's profile (resume test set)
  python scripts/ingest.py /path/to/docs                # generic enterprise documents
  python scripts/ingest.py --to-neo4j                   # copy the memory snapshot into Neo4j
"""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crag.ingest import SUPPORTED, ingest_file  # noqa: E402
from crag.store import MemoryStore, Neo4jStore, copy_memory_to_neo4j, get_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--profiles", action="store_true", help="treat each file as one employee profile")
    ap.add_argument("--to-neo4j", action="store_true", help="copy the memory snapshot into Neo4j")
    args = ap.parse_args()

    if args.to_neo4j:
        mem = MemoryStore()
        copy_memory_to_neo4j(mem, Neo4jStore())
        print("Copied", mem.stats(), "to Neo4j")
        return

    store = get_store()
    done = {d["source"] for d in store.documents()}  # resumable: skip files already ingested
    files = sorted(p for p in Path(args.folder).iterdir() if p.suffix.lower() in SUPPORTED)
    for i, f in enumerate(files, 1):
        if f.name in done:
            continue
        subject = None
        if args.profiles:
            # The test resumes are anonymised; the numeric file id stands in for the employee's name.
            subject = "Employee " + re.findall(r"\d+", f.stem)[-1]
        t0 = time.time()
        try:
            r = ingest_file(store, f, subject)
            print(f"[{i}/{len(files)}] {f.name}: {r} in {time.time() - t0:.1f}s", flush=True)
        except Exception as e:
            print(f"[{i}/{len(files)}] {f.name}: FAILED {e}", flush=True)
    print("Done:", store.stats())


if __name__ == "__main__":
    main()
