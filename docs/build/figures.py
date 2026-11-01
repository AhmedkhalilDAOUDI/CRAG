"""Static figures for the report and slides (written to docs/build/fig/)."""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIG = HERE / "fig"
FIG.mkdir(exist_ok=True)
CLAY, INK, GREY, OLIVE, BLUE, PAPER = "#C2643F", "#191917", "#8A8880", "#6A7A4F", "#3F5F7A", "#FAF9F5"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": "white"})


def gantt():
    phases = [("Study of the subject and literature", 0, 3), ("Architecture and data model", 2, 3),
              ("Ingestion pipeline (OCR, extraction)", 4, 4), ("Graph store and query workflow", 7, 4),
              ("Interface, API, deployment", 10, 3), ("Evaluation", 12, 3), ("Report and defence", 13, 4)]
    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=200)
    for i, (name, start, dur) in enumerate(phases):
        ax.barh(i, dur, left=start, color=CLAY if i % 2 == 0 else INK, height=0.55)
    ax.set_yticks(range(len(phases)), [p[0] for p in phases]); ax.invert_yaxis()
    ax.set_xticks(range(0, 18, 2), [f"W{w + 1}" for w in range(0, 18, 2)]); ax.set_xlabel("week (dotted lines: the seven supervisor meetings)")
    for m in (2, 4, 6, 9, 11, 13, 15):  # the seven supervisor meetings (MEETING folder)
        ax.axvline(m, color=GREY, lw=0.6, ls=":")
    fig.tight_layout(); fig.savefig(FIG / "gantt.png"); plt.close(fig)


def positioning():
    pts = [("Classic RAG", 1, 1), ("Corrective RAG", 1.6, 1.5), ("Self-RAG", 2.6, 1.7), ("LightRAG", 3.2, 3.4),
           ("HippoRAG", 3.6, 4.2), ("Think-on-Graph", 1.5, 4.3), ("MS GraphRAG", 4.6, 3.6), ("CRAG", 3.0, 4.6)]
    fig, ax = plt.subplots(figsize=(6, 4), dpi=200)
    for name, x, y in pts:
        c = CLAY if name == "CRAG" else INK
        ax.scatter(x, y, s=160 if name == "CRAG" else 60, color=c, zorder=3)
        ax.annotate(name, (x, y), xytext=(7, 5), textcoords="offset points", fontsize=9, color=c,
                    fontweight="bold" if name == "CRAG" else "normal")
    ax.set_xlim(0.5, 5.2); ax.set_ylim(0.5, 5.2); ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlabel("indexing cost and complexity  →"); ax.set_ylabel("relational / multi-hop reasoning  →")
    ax.text(0.6, 0.62, "qualitative positioning", fontsize=7, color=GREY)
    fig.tight_layout(); fig.savefig(FIG / "positioning.png"); plt.close(fig)


def entity_types():
    stats = json.loads((ROOT / "data" / "index" / "graph.json").read_text())
    counts = {}
    for e in stats["entities"].values():
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    items = sorted(counts.items(), key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(6.4, 3.6), dpi=200)
    ax.barh([k for k, _ in items], [v for _, v in items], color=[CLAY if k == "Person" else INK for k, _ in items])
    for i, (_, v) in enumerate(items):
        ax.text(v + max(counts.values()) * 0.01, i, str(v), va="center", fontsize=8)
    ax.set_xlabel("number of entities")
    fig.tight_layout(); fig.savefig(FIG / "entity_types.png"); plt.close(fig)


if __name__ == "__main__":
    which = sys.argv[1:] or ["gantt", "positioning", "entity_types"]
    for name in which:
        globals()[name]()
        print("wrote", name)
