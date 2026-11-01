"""Markdown -> styled HTML -> PDF (headless Chrome), with a second pass that writes real page numbers into the TOC.

Usage: python pdfdoc.py source.md out.pdf [--cover cover.html]
Markdown conventions: '# ' = chapter (new page), '## ' / '### ' = sections; [[TOC]] places the table of contents.
"""
import base64
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown
from pypdf import PdfReader

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HERE = Path(__file__).resolve().parent

CSS = """
@page { size: A4; margin: 24mm 22mm 24mm 24mm;
  @bottom-center { content: counter(page); font: 9.5pt 'Public Sans', sans-serif; color: #5E5D59; } }
@page :first { @bottom-center { content: none; } }
@page cover { margin: 0; @bottom-center { content: none; } }
* { box-sizing: border-box; }
body { font: 11pt/1.62 'Newsreader', Georgia, serif; color: #191917; margin: 0; }
h1, h2, h3, h4 { font-family: 'Newsreader', Georgia, serif; font-weight: 500; line-height: 1.2; break-after: avoid; }
h1 { font-size: 27pt; margin: 0 0 18pt; break-before: page; letter-spacing: -0.01em; }
h1 .num { display: block; font: 600 10pt 'Public Sans', sans-serif; color: #C2643F; margin-bottom: 8pt; }
h2 { font-size: 16pt; margin: 22pt 0 8pt; }
h3 { font-size: 12.5pt; margin: 16pt 0 6pt; }
h4 { font-size: 11pt; margin: 12pt 0 4pt; font-style: italic; }
p { margin: 0 0 8pt; text-align: justify; hyphens: auto; orphans: 3; widows: 3; }
ul, ol { margin: 0 0 9pt; padding-left: 18pt; } li { margin-bottom: 3pt; }
a { color: inherit; text-decoration: none; }
code { font: 9pt Menlo, monospace; background: #F0EEE6; padding: 0 3px; border-radius: 3px; }
pre { background: #F0EEE6; padding: 9pt 11pt; border-radius: 6px; font: 8.6pt/1.45 Menlo, monospace; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 12pt; font: 9.3pt/1.4 'Public Sans', sans-serif; break-inside: avoid; }
th { text-align: left; border-bottom: 1.5px solid #191917; padding: 5pt 6pt; font-weight: 600; }
td { border-bottom: 0.6px solid #CFCDC2; padding: 4.5pt 6pt; vertical-align: top; }
figure { margin: 10pt 0 14pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 150mm; }
figcaption, .tcap { font: 9pt/1.4 'Public Sans', sans-serif; color: #5E5D59; margin-top: 5pt; text-align: center; }
.tcap { margin: 10pt 0 2pt; }
blockquote { margin: 8pt 0; padding: 6pt 12pt; border-left: 3px solid #C2643F; background: #FAF9F5; }
blockquote p { margin: 0; }
.box { border: 1px solid #CFCDC2; border-radius: 8px; padding: 9pt 12pt; margin: 10pt 0; background: #FAF9F5; break-inside: avoid; }
.box p:last-child { margin: 0; }
.toc { list-style: none; padding: 0; font: 10.5pt/1.5 'Public Sans', sans-serif; }
.toc li { display: flex; gap: 6pt; margin: 0; }
.toc li.l1 { font-weight: 600; margin-top: 7pt; }
.toc li.l2 { padding-left: 16pt; } .toc li.l3 { padding-left: 32pt; font-size: 9.6pt; color: #3a3a37; }
.toc .dots { flex: 1; border-bottom: 1px dotted #9a988f; margin-bottom: 4pt; }
.front h1 { break-before: page; }
.eq { text-align: center; font-style: italic; margin: 6pt 0 10pt; }
"""

FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;'
         '1,6..72,400&family=Public+Sans:wght@400;600&display=swap" rel="stylesheet">')


def inline_images(html: str, base: Path) -> str:
    def rep(m):
        p = (base / m.group(1)).resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        return f'src="data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}"'
    return re.sub(r'src="(?!data:|https?:)([^"]+)"', rep, html)


def build_html(md_text: str, cover: str, pages: dict | None) -> tuple[str, list]:
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "attr_list", "md_in_html"])
    heads, chap = [], 0

    def number(m):
        nonlocal chap
        level, text = int(m.group(1)), m.group(2)
        hid = f"h{len(heads)}"
        plain = re.sub(r"<[^>]+>", "", text)
        if level == 1 and not plain.startswith(("Acknowledg", "Abstract", "Résumé", "Table of", "List of", "Abbrev",
                                                "General", "References", "Appendix", "Preface", "How to")):
            chap += 1
            text = f'<span class="num">Chapter {chap}</span>{text}'
        if level <= 3:
            heads.append((level, plain, hid))
        return f'<h{level} id="{hid}">{text}</h{level}>'

    body = re.sub(r"<h([1-3])>(.*?)</h\1>", number, body)
    toc_items = []
    for level, plain, hid in heads:
        if plain in ("Table of contents",):
            continue
        pg = (pages or {}).get(hid, "")
        toc_items.append(f'<li class="l{level}"><a href="#{hid}">{plain}</a><span class="dots"></span><span>{pg}</span></li>')
    body = body.replace("<p>[[TOC]]</p>", f'<ul class="toc">{"".join(toc_items)}</ul>')
    html = f'<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{CSS}</style></head><body>{cover}{body}</body></html>'
    return html, heads


def to_pdf(html: str, out: Path):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=8000",
                    f"--print-to-pdf={out}", f"file://{f.name}"], check=True, capture_output=True)


def find_pages(pdf: Path, heads: list, skip_pages: int) -> dict:
    texts = [re.sub(r"\s+", " ", p.extract_text() or "") for p in PdfReader(pdf).pages]
    pages, start = {}, skip_pages
    for level, plain, hid in heads:
        key = re.sub(r"\s+", " ", plain).strip()[:40]
        for i in range(start, len(texts)):
            if key in texts[i]:
                pages[hid] = i + 1
                start = i  # headings appear in order
                break
    return pages


def build(md_path: Path, out: Path, cover_html: str = ""):
    md_text = md_path.read_text()
    html, heads = build_html(md_text, cover_html, None)
    html = inline_images(html, md_path.parent)
    to_pdf(html, out)
    toc_page = next((i for i, t in enumerate(PdfReader(out).pages) if "Table of contents" in (t.extract_text() or "")), 0)
    pages = find_pages(out, heads, toc_page + 1)
    html, _ = build_html(md_text, cover_html, pages)
    to_pdf(inline_images(html, md_path.parent), out)
    print(f"{out.name}: {len(PdfReader(out).pages)} pages, {len(pages)}/{len(heads)} headings located")


if __name__ == "__main__":
    md, out = Path(sys.argv[1]), Path(sys.argv[2])
    cover = Path(sys.argv[sys.argv.index("--cover") + 1]).read_text() if "--cover" in sys.argv else ""
    build(md, out, cover)
