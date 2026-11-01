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
      font-family: 'Public Sans', sans-serif; color: #191917; background: #FFFFFF;">
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
        "SH_LAT_G": f2(v1["single_hop"]["graph"]["latency_mean_s"]), "SH_LAT_V": f2(v1["single_hop"]["vector"]["latency_mean_s"]),
        "SH_P95_G": f2(v1["single_hop"]["graph"]["latency_p95_s"]), "SH_P95_V": f2(v1["single_hop"]["vector"]["latency_p95_s"]),
        "REL_EM_G": f2(rl["graph"]["exact_match"]), "REL_EM_V": f2(rl["vector"]["exact_match"]),
        "REL_HIT_G": f2(rl["graph"]["hit_rate"]), "REL_HIT_V": f2(rl["vector"]["hit_rate"]),
        "REL_LAT_G": f2(v1["relational"]["graph"]["latency_mean_s"]), "REL_LAT_V": f2(v1["relational"]["vector"]["latency_mean_s"]),
        "V1_EXP_CRAG": f2(v1["experts"]["crag_p5"]), "V1_EXP_BASE": f2(v1["experts"]["baseline_p5"]),
        "V1_SH_HIT_G": f2(v1["single_hop"]["graph"]["hit_rate"]), "V1_SH_HIT_V": f2(v1["single_hop"]["vector"]["hit_rate"]),
        "V1_SH_COR_G": f2(v1["single_hop"]["graph"]["correctness"]), "V1_SH_COR_V": f2(v1["single_hop"]["vector"]["correctness"]),
        "V1_SH_FAI_G": f2(v1["single_hop"]["graph"]["faithfulness"]), "V1_SH_FAI_V": f2(v1["single_hop"]["vector"]["faithfulness"]),
        "V1_REL_HIT_G": f2(v1["relational"]["graph"]["hit_rate"]), "V1_REL_HIT_V": f2(v1["relational"]["vector"]["hit_rate"]),
        "V1_SH_LAT_G": f2(v1["single_hop"]["graph"]["latency_mean_s"]), "V1_SH_LAT_V": f2(v1["single_hop"]["vector"]["latency_mean_s"]),
        "V1_SH_P95_G": f2(v1["single_hop"]["graph"]["latency_p95_s"]), "V1_SH_P95_V": f2(v1["single_hop"]["vector"]["latency_p95_s"]),
        "V1_REL_EM_G": f2(v1["relational"]["graph"]["exact_match"]), "V1_REL_EM_V": f2(v1["relational"]["vector"]["exact_match"]),
        "RESULTS_ANSWER": (
            f"**Short.** The graph is decisive on relational questions: CRAG named the right employee in "
            f"{pct(rl['graph']['exact_match'])} of them, classic RAG in {pct(rl['vector']['exact_match'])}. On broad "
            f"expert queries both reach P@5 = {f2(s['experts']['crag_p5'])} vs {f2(s['experts']['baseline_p5'])}; on "
            f"simple single-passage questions both retrieve equally well (hit rate {f2(sh['graph']['hit_rate'])} vs "
            f"{f2(sh['vector']['hit_rate'])}) and CRAG's judged answers are slightly better, but CRAG is slower "
            f"(about {f2(v1['single_hop']['graph']['latency_mean_s'])} s vs {f2(v1['single_hop']['vector']['latency_mean_s'])} s per question).\n\n**Detail.** These are second-iteration numbers. The first "
            f"run exposed flaws in my evaluation (the baseline could not see person names, the judge did not see graph "
            f"facts, fusion displaced the best passage) and a degree bias in expert ranking. I fixed them and re-ran, "
            f"and I report both runs, because the fixes were made after seeing the first results on the same questions."),
    }


def fill(text: str, vals: dict) -> str:
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals[m.group(1)]), text)
    assert "{{" not in out, "unfilled placeholder"
    return out


def build_pdf(src_names, out: Path, vals, cover_html, kicker="Chapter"):
    md = "\n\n".join((HERE / n).read_text() for n in src_names)
    tmp = HERE / "_build.md"
    tmp.write_text(fill(md, vals))
    try:
        pdfdoc.build(tmp, out, cover_html, kicker)
    finally:
        tmp.unlink()


def keynote_pdf(pptx: Path, pdf: Path):
    """Export through Keynote (macOS); the files must live outside Keynote-unreadable folders, hence /tmp."""
    if subprocess.run(["pgrep", "-x", "Keynote"], capture_output=True).returncode:
        subprocess.run(["open", "-ga", "Keynote"], check=True)
        subprocess.run(["sleep", "6"])
    tmp_pdf = pptx.with_suffix(".pdf")
    subprocess.run(["osascript", str(HERE / "keynote_export.applescript"), str(pptx), str(tmp_pdf)],
                   check=True, capture_output=True, timeout=300)
    shutil.copy(tmp_pdf, pdf)


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
                    "Fifty likely questions from the jury, with short and detailed answers"), kicker="Part")
    build_pdf(["course.md"], DETAILS_DIR / "CRAG_Course_From_Zero_to_100.pdf", vals,
              cover("Course", "CRAG from first principles",
                    "Everything used in the project, explained from zero: computers, models, retrieval, graphs, engineering"))

    texts = decks_text(x)
    build_decks(x, texts, REPORT_DIR / "CRAG_Defence_Presentation.pptx", MEET_DIR)
    if sys.platform == "darwin" and "--no-keynote" not in sys.argv:
        # PDF copies come from a notes-free build: Keynote crashes on python-pptx speaker notes.
        import slides
        tmp = Path("/tmp/crag_decks")
        shutil.rmtree(tmp, ignore_errors=True)
        slides.NOTES = False
        build_decks(x, texts, tmp / "CRAG_Defence_Presentation.pptx", tmp)
        slides.NOTES = True
        targets = {"CRAG_Defence_Presentation.pptx": REPORT_DIR}
        for p in sorted(tmp.glob("*.pptx")):
            out = targets.get(p.name, MEET_DIR) / p.with_suffix(".pdf").name
            keynote_pdf(p, out)
            print("pdf", out.name)


def build_decks(x, texts, final_path, meet_dir):
    meet_dir.mkdir(parents=True, exist_ok=True)
    decks.final(final_path, x, **texts)
    decks.m1(meet_dir)
    decks.m2(meet_dir, x)
    decks.m3(meet_dir, x)
    decks.m4(meet_dir, x)
    decks.m5(meet_dir, x)
    decks.m6(meet_dir, x)
    decks.m7(meet_dir, x, texts["why_main"], texts["why_quality"], texts["limits"])


def decks_text(x):
    """Slide narrative for the results: kept here, next to the numbers it describes."""
    from decks_text import TEXT
    return TEXT(x)


if __name__ == "__main__":
    main()
