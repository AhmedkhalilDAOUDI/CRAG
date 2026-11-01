"""Small python-pptx toolkit for CRAG decks: 16:9, ivory paper, serif titles, native charts, speaker notes."""
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

PAPER, PAPER2 = RGBColor(0xFA, 0xF9, 0xF5), RGBColor(0xF0, 0xEE, 0xE6)
INK, INK2 = RGBColor(0x19, 0x19, 0x17), RGBColor(0x5E, 0x5D, 0x59)
CLAY, OLIVE, GREY, LINE = RGBColor(0xC2, 0x64, 0x3F), RGBColor(0x6A, 0x7A, 0x4F), RGBColor(0x8A, 0x88, 0x80), RGBColor(0xCF, 0xCD, 0xC2)
SERIF, SANS = "Georgia", "Arial"
HERE = Path(__file__).resolve().parent
LOGO = HERE / "ehtp_logo.png"
W, H = Inches(13.333), Inches(7.5)
NOTES = True  # Keynote crashes importing python-pptx notes slides; PDF exports are built with NOTES = False


class Deck:
    def __init__(self, footer: str):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = W, H
        self.footer = footer
        self.n = 0

    # ---------- primitives
    def _slide(self, notes: str = ""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = PAPER
        self.n += 1
        if notes and NOTES:
            s.notes_slide.notes_text_frame.text = notes
        return s

    @staticmethod
    def text(s, x, y, w, h, txt, size=18, color=INK, font=SANS, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Emu(0)
        for i, line in enumerate(txt if isinstance(txt, list) else [txt]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            r = p.add_run()
            r.text = line
            r.font.size, r.font.color.rgb, r.font.name, r.font.bold, r.font.italic = Pt(size), color, font, bold, italic
        return tb

    def _chrome(self, s, title, kicker=None):
        if kicker:
            self.text(s, Inches(0.7), Inches(0.42), Inches(11), Inches(0.35), kicker, 13, CLAY, SANS, bold=True)
        self.text(s, Inches(0.7), Inches(0.72), Inches(11.9), Inches(1.0), title, 32, INK, SERIF)
        self.text(s, Inches(0.7), Inches(7.0), Inches(9), Inches(0.3), self.footer, 10, GREY)
        self.text(s, Inches(11.6), Inches(7.0), Inches(1.0), Inches(0.3), str(self.n), 10, GREY, align=PP_ALIGN.RIGHT)

    @staticmethod
    def bullets(s, x, y, w, h, items, size=18, color=INK, gap=8):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        for i, it in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(gap)
            sub = it.startswith("  ")
            r0 = p.add_run()
            r0.text = ("–  " if sub else "•  ")
            r0.font.size, r0.font.color.rgb, r0.font.name = Pt(size - (2 if sub else 0)), CLAY, SANS
            r = p.add_run()
            r.text = it.strip()
            r.font.size, r.font.color.rgb, r.font.name = Pt(size - (2 if sub else 0)), color if not sub else INK2, SANS
            if sub:
                p.level = 1
        return tb

    def explain(self, s, txt, x=Inches(0.7), y=Inches(6.05), w=Inches(11.9)):
        """The explanation band at the bottom of a slide."""
        box = s.shapes.add_shape(1, x, y, w, Inches(0.8))
        box.fill.solid(); box.fill.fore_color.rgb = PAPER2; box.line.fill.background()
        box.shadow.inherit = False
        tf = box.text_frame
        tf.margin_left = tf.margin_right = Inches(0.2)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.word_wrap = True
        p = tf.paragraphs[0]
        r = p.add_run(); r.text = "Why it matters  "
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(12), True, CLAY, SANS
        r = p.add_run(); r.text = txt
        r.font.size, r.font.color.rgb, r.font.name = Pt(13), INK, SANS

    # ---------- slide types
    def cover(self, title, subtitle, lines, notes=""):
        s = self._slide(notes)
        if LOGO.exists():
            s.shapes.add_picture(str(LOGO), Inches(0.7), Inches(0.55), height=Inches(0.75))
        self.text(s, Inches(0.7), Inches(2.0), Inches(11.5), Inches(1.6), title, 44, INK, SERIF)
        self.text(s, Inches(0.7), Inches(3.55), Inches(11), Inches(0.9), subtitle, 20, INK2, SANS)
        bar = s.shapes.add_shape(1, Inches(0.7), Inches(4.6), Inches(0.9), Inches(0.06))
        bar.fill.solid(); bar.fill.fore_color.rgb = CLAY; bar.line.fill.background()
        self.text(s, Inches(0.7), Inches(4.85), Inches(11), Inches(1.8), lines, 15, INK, SANS)
        return s

    def section(self, number, title, sub="", notes=""):
        s = self._slide(notes)
        self.text(s, Inches(0.7), Inches(2.3), Inches(3), Inches(1.4), str(number), 80, CLAY, SERIF)
        self.text(s, Inches(0.7), Inches(3.75), Inches(11.5), Inches(1.2), title, 38, INK, SERIF)
        if sub:
            self.text(s, Inches(0.7), Inches(4.75), Inches(11), Inches(0.8), sub, 18, INK2)
        return s

    def points(self, title, items, why=None, kicker=None, notes="", size=19):
        s = self._slide(notes)
        self._chrome(s, title, kicker)
        self.bullets(s, Inches(0.7), Inches(1.85), Inches(11.9), Inches(4.1), items, size)
        if why:
            self.explain(s, why)
        return s

    def two_col(self, title, left_title, left, right_title, right, why=None, kicker=None, notes=""):
        s = self._slide(notes)
        self._chrome(s, title, kicker)
        for i, (t, items) in enumerate(((left_title, left), (right_title, right))):
            x = Inches(0.7 + i * 6.15)
            self.text(s, x, Inches(1.85), Inches(5.8), Inches(0.5), t, 20, CLAY if i else INK, SERIF)
            self.bullets(s, x, Inches(2.45), Inches(5.8), Inches(3.5), items, 16)
        if why:
            self.explain(s, why)
        return s

    def image(self, title, path, caption=None, why=None, kicker=None, notes="", max_h=4.15):
        s = self._slide(notes)
        self._chrome(s, title, kicker)
        from PIL import Image
        iw, ih = Image.open(path).size
        top = Inches(1.8)
        avail_w, avail_h = 11.9, (max_h if why else max_h + 0.8)
        scale = min(avail_w / iw, avail_h / ih)
        w, h = iw * scale, ih * scale
        s.shapes.add_picture(str(path), Inches(0.7 + (avail_w - w) / 2), top, Inches(w), Inches(h))
        if caption:
            self.text(s, Inches(0.7), top + Inches(h) + Inches(0.05), Inches(11.9), Inches(0.3), caption, 11, INK2, align=PP_ALIGN.CENTER)
        if why:
            self.explain(s, why)
        return s

    def chart(self, title, categories, series: dict, why=None, kicker=None, notes="", kind="bar", number_format='0.00',
              side_text=None, y_max=None):
        s = self._slide(notes)
        self._chrome(s, title, kicker)
        cd = CategoryChartData()
        cd.categories = categories
        for name, vals in series.items():
            cd.add_series(name, vals)
        ct = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED, "hbar": XL_CHART_TYPE.BAR_CLUSTERED, "pie": XL_CHART_TYPE.DOUGHNUT}[kind]
        cw = Inches(7.6 if side_text else 11.9)
        gf = s.shapes.add_chart(ct, Inches(0.7), Inches(1.8), cw, Inches(4.1 if why else 4.9), cd)
        ch = gf.chart
        ch.font.size, ch.font.name, ch.font.color.rgb = Pt(12), SANS, INK
        ch.has_legend = len(series) > 1 or kind == "pie"
        if ch.has_legend:
            ch.legend.position = XL_LEGEND_POSITION.TOP if kind != "pie" else XL_LEGEND_POSITION.RIGHT
            ch.legend.include_in_layout = False
        palette = [CLAY, GREY, OLIVE, INK, LINE]
        if kind == "pie":
            for i, pt in enumerate(ch.plots[0].series[0].points):
                pt.format.fill.solid(); pt.format.fill.fore_color.rgb = [CLAY, INK, OLIVE, GREY, LINE, INK2][i % 6]
        else:
            plot = ch.plots[0]
            plot.gap_width = 60
            plot.has_data_labels = True
            plot.data_labels.number_format, plot.data_labels.number_format_is_linked = number_format, False
            plot.data_labels.font.size = Pt(11)
            for i, ser in enumerate(plot.series):
                ser.format.fill.solid(); ser.format.fill.fore_color.rgb = palette[i % len(palette)]
            va = ch.value_axis
            va.has_major_gridlines = False
            va.tick_labels.font.size = Pt(10)
            if y_max is not None:
                va.maximum_scale = y_max
                va.minimum_scale = 0
        if side_text:
            self.bullets(s, Inches(8.7), Inches(2.0), Inches(3.9), Inches(3.9), side_text, 15)
        if why:
            self.explain(s, why)
        return s

    def table(self, title, header, rows, why=None, kicker=None, notes="", col_w=None, size=13):
        s = self._slide(notes)
        self._chrome(s, title, kicker)
        h = Inches(0.42) * (len(rows) + 1)
        t = s.shapes.add_table(len(rows) + 1, len(header), Inches(0.7), Inches(1.85), Inches(11.9), h).table
        for j, w in enumerate(col_w or []):
            t.columns[j].width = Inches(w)
        for i, row in enumerate([header] + rows):
            for j, val in enumerate(row):
                c = t.cell(i, j)
                c.text = str(val)
                c.fill.solid(); c.fill.fore_color.rgb = INK if i == 0 else (PAPER2 if i % 2 else PAPER)
                for p in c.text_frame.paragraphs:
                    for r in p.runs:
                        r.font.size, r.font.name = Pt(size), SANS
                        r.font.color.rgb = PAPER if i == 0 else INK
                        r.font.bold = i == 0
        if why:
            self.explain(s, why)
        return s

    def quote(self, text, sub="", notes=""):
        s = self._slide(notes)
        self.text(s, Inches(1.2), Inches(2.2), Inches(10.9), Inches(2.6), text, 34, INK, SERIF, anchor=MSO_ANCHOR.MIDDLE)
        if sub:
            self.text(s, Inches(1.2), Inches(4.9), Inches(10.9), Inches(0.6), sub, 16, INK2)
        return s

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(path)
        print("saved", path, self.n, "slides")
