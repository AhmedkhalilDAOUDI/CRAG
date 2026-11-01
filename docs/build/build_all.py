"""Build every deliverable from the sources in this folder and the real project data.

  python docs/build/build_all.py            # PDFs + decks (+ Keynote PDF export on macOS)
Outputs go to the CRAG deliverable folders next to CODE/.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent.parent            # CODE/
OUT = ROOT.parent                    # CRAG/
REPORT_DIR, MEET_DIR, DETAILS_DIR = OUT / "RAPPORT ET PRESENTATION", OUT / "MEETING", OUT / "DETAILS"

import decks  # noqa: E402
import pdfdoc  # noqa: E402


def cover(kind: str, title: str, subtitle: str) -> str:
    return f"""<section style="page: cover; height: 297mm; padding: 26mm 24mm; display: flex; flex-direction: column;
      font-family: 'Public Sans', sans-serif; color: #191917; background: #FAF9F5;">
  <img src="ehtp_logo.png" style="width: 92mm;">
  <div style="margin-top: 34mm; font: 600 10.5pt 'Public Sans'; color: #C2643F;">{kind}</div>
  <div style="font: 400 34pt/1.08 'Newsreader', serif; margin: 6mm 0 6mm; letter-spacing: -0.01em;">{title}</div>
  <div style="font: 400 14pt/1.4 'Public Sans'; color: #5E5D59; max-width: 140mm;">{subtitle}</div>
  <div style="width: 22mm; height: 1.4mm; background: #C2643F; margin: 14mm 0 10mm;"></div>
  <table style="font: 11pt/1.7 'Public Sans'; border: 0; width: auto; margin: 0;">
    <tr><td style="border:0; padding:0 8mm 0 0; color:#5E5D59;">Presented by</td><td style="border:0; padding:0;">Daoudi Ahmed Khalil</td></tr>
    <tr><td style="border:0; padding:0 8mm 0 0; color:#5E5D59;">Supervised by</td><td style="border:0; padding:0;">Dr. Abdelali El Bouchti</td></tr>
    <tr><td style="border:0; padding:0 8mm 0 0; color:#5E5D59;">Degree</td><td style="border:0; padding:0;">Master in Data Science and Engineering (MDSE)</td></tr>
    <tr><td style="border:0; padding:0 8mm 0 0; color:#5E5D59;">Institution</td><td style="border:0; padding:0;">Ecole Hassania des Travaux Publics</td></tr>
    <tr><td style="border:0; padding:0 8mm 0 0; color:#5E5D59;">Academic year</td><td style="border:0; padding:0;">2025/2026</td></tr>
  </table>
</section>"""


def values():
    x = decks.data()
    s, v1 = x["s"], json.loads((ROOT / "data" / "eval" / "results_v1.json").read_text())["summary"]
    f2, pct = (lambda v: f"{v:.2f}"), (lambda v: f"{100 * v:.0f}%")
    sh, rl = s["single_hop"], s["relational"]
    return x, {
        "N_DOCS": x["n_docs"], "N_CHUNKS": x["n_chunks"], "N_ENT": f"{x['n_ent']:,}", "N_REL": f"{x['n_rel']:,}",
        "N_EXP": s["experts"]["n"], "N_SH": sh["graph"]["n"], "N_RELQ": rl["graph"]["n"],
        "EXP_CRAG": f2(s["experts"]["crag_p5"]), "EXP_BASE": f2(s["experts"]["baseline_p5"]),
        "SH_HIT_G": f2(sh["graph"]["hit_rate"]), "SH_HIT_V": f2(sh["vector"]["hit_rate"]),
        "SH_COR_G": f2(sh["graph"]["correctness"]), "SH_COR_V": f2(sh["vector"]["correctness"]),
        "SH_FAI_G": f2(sh["graph"]["faithfulness"]), "SH_FAI_V": f2(sh["vector"]["faithfulness"]),
        "SH_LAT_G": f2(sh["graph"]["latency_mean_s"]), "SH_LAT_V": f2(sh["vector"]["latency_mean_s"]),
        "SH_P95_G": f2(sh["graph"]["latency_p95_s"]), "SH_P95_V": f2(sh["vector"]["latency_p95_s"]),
        "REL_EM_G": f2(rl["graph"]["exact_match"]), "REL_EM_V": f2(rl["vector"]["exact_match"]),
        "REL_HIT_G": f2(rl["graph"]["hit_rate"]), "REL_HIT_V": f2(rl["vector"]["hit_rate"]),
        "REL_LAT_G": f2(rl["graph"]["latency_mean_s"]), "REL_LAT_V": f2(rl["vector"]["latency_mean_s"]),
        "V1_EXP_CRAG": f2(v1["experts"]["crag_p5"]), "V1_EXP_BASE": f2(v1["experts"]["baseline_p5"]),
        "V1_SH_HIT_G": f2(v1["single_hop"]["graph"]["hit_rate"]), "V1_SH_HIT_V": f2(v1["single_hop"]["vector"]["hit_rate"]),
        "V1_SH_COR_G": f2(v1["single_hop"]["graph"]["correctness"]), "V1_SH_COR_V": f2(v1["single_hop"]["vector"]["correctness"]),
        "V1_SH_FAI_G": f2(v1["single_hop"]["graph"]["faithfulness"]), "V1_SH_FAI_V": f2(v1["single_hop"]["vector"]["faithfulness"]),
        "V1_REL_EM_G": f2(v1["relational"]["graph"]["exact_match"]), "V1_REL_EM_V": f2(v1["relational"]["vector"]["exact_match"]),
        "PCT": pct,
    }


def fill(text: str, vals: dict) -> str:
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals[m.group(1)]), text)
    assert "{{" not in out, "unfilled placeholder"
    return out


def build_pdf(src_names, out: Path, vals, cover_html):
    md = "\n\n".join((HERE / n).read_text() for n in src_names)
    tmp = HERE / "_build.md"
    tmp.write_text(fill(md, vals))
    try:
        pdfdoc.build(tmp, out, cover_html)
    finally:
        tmp.unlink()


def keynote_pdf(pptx: Path):
    pdf = pptx.with_suffix(".pdf")
    script = (f'tell application "Keynote"\nset d to open POSIX file "{pptx}"\n'
              f'export d to POSIX file "{pdf}" as PDF\nclose d saving no\nend tell')
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=300)


def main():
    for f in ("retrieval_comparison.png", "answer_quality.png", "latency.png"):
        shutil.copy(ROOT / "docs" / "eval" / f, HERE / "fig" / f)
    import figures
    figures.entity_types()
    x, vals = values()
    REPORT_DIR.mkdir(exist_ok=True)
    MEET_DIR.mkdir(exist_ok=True)

    build_pdf(["report.md", "report_ch5.md"], REPORT_DIR / "CRAG_Final_Report.pdf", vals,
              cover("Final-year project report (Projet de Fin d'Études)",
                    "CRAG: A Knowledge-Graph-Augmented LLM Platform for Enterprise Knowledge Management",
                    "Knowledge Graph + LLM: extracting, connecting and explaining company knowledge"))
    build_pdf(["jury_qa.md"], REPORT_DIR / "CRAG_Jury_Questions_and_Answers.pdf", vals,
              cover("Defence preparation", "CRAG: jury questions and answers",
                    "Fifty likely questions from the jury, with short and detailed answers"))
    build_pdf(["course.md"], DETAILS_DIR / "CRAG_Course_From_Zero_to_100.pdf", vals,
              cover("Course", "CRAG from first principles",
                    "Everything used in the project, explained from zero: computers, models, retrieval, graphs, engineering"))

    texts = decks_text(x)
    final_path = REPORT_DIR / "CRAG_Defence_Presentation.pptx"
    decks.final(final_path, x, **texts)
    decks.m1(MEET_DIR)
    decks.m2(MEET_DIR, x)
    decks.m3(MEET_DIR, x)
    decks.m4(MEET_DIR, x)
    decks.m5(MEET_DIR, x)
    decks.m6(MEET_DIR, x)
    decks.m7(MEET_DIR, x, texts["why_main"], texts["why_quality"], texts["limits"])
    if sys.platform == "darwin" and "--no-keynote" not in sys.argv:
        for p in [final_path, *sorted(MEET_DIR.glob("*.pptx"))]:
            keynote_pdf(p)
            print("pdf", p.with_suffix(".pdf").name)


def decks_text(x):
    """Slide narrative for the results: kept here, next to the numbers it describes."""
    from decks_text import TEXT
    return TEXT(x)


if __name__ == "__main__":
    main()
