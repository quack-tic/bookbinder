"""
epub_to_pdf.py  —  EPUB → PDF Konverter mit klickbarem Inhaltsverzeichnis
Benötigt: pip install ebooklib fpdf2 pypdf

Starten:
  python epub_to_pdf.py              # GUI
  python epub_to_pdf.py buch.epub    # ohne GUI
  python epub_to_pdf.py buch.epub ausgabe.pdf
"""

import os, re, sys, base64, threading, io
import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Fonts
# ─────────────────────────────────────────────────────────────────────────────

def _find_fonts():
    candidates = {
        "win_serif": {
            "":   r"C:\Windows\Fonts\times.ttf",
            "B":  r"C:\Windows\Fonts\timesbd.ttf",
            "I":  r"C:\Windows\Fonts\timesi.ttf",
            "BI": r"C:\Windows\Fonts\timesbi.ttf",
        },
        "win_sans": {
            "":   r"C:\Windows\Fonts\arial.ttf",
            "B":  r"C:\Windows\Fonts\arialbd.ttf",
            "I":  r"C:\Windows\Fonts\ariali.ttf",
            "BI": r"C:\Windows\Fonts\arialbi.ttf",
        },
        "dv_serif": {
            "":   "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
            "B":  "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "I":  "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
            "BI": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-BoldItalic.ttf",
        },
        "dv_sans": {
            "":   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "B":  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "I":  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "BI": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
        },
        "lib_serif": {
            "":   "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "B":  "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
            "I":  "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
            "BI": "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
        },
        "lib_sans": {
            "":   "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "B":  "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "I":  "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
            "BI": "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
        },
    }
    ok = lambda d: all(Path(v).exists() for v in d.values())
    body = next((candidates[k] for k in ("win_serif","dv_serif","lib_serif") if ok(candidates[k])), None)
    head = next((candidates[k] for k in ("win_sans", "dv_sans", "lib_sans")  if ok(candidates[k])), None)
    return body, head


# ─────────────────────────────────────────────────────────────────────────────
# HTML-Bereinigung
# ─────────────────────────────────────────────────────────────────────────────

MIME_MAP = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
            "gif":"image/gif","webp":"image/webp"}


def _clean_html(raw: str, item_name: str, images: dict) -> str:
    m = re.search(r"<body[^>]*>(.*?)</body>", raw, re.DOTALL | re.IGNORECASE)
    html = m.group(1) if m else raw

    # Entferne Style/Script/Meta
    for tag in ("style","link","script","meta"):
        html = re.sub(rf"<{tag}[^>]*/?>.*?</{tag}>", "", html, flags=re.DOTALL|re.IGNORECASE)
        html = re.sub(rf"<{tag}[^>]*/?>", "", html, flags=re.IGNORECASE)

    # Bilder einbetten
    base_dir = os.path.dirname(item_name)
    def _embed(m):
        src = m.group(1)
        if src.startswith("data:"): return m.group(0)
        resolved = os.path.normpath(os.path.join(base_dir, src)).replace("\\","/").lstrip("/")
        b64 = images.get(resolved) or images.get(os.path.basename(src))
        return f'<img src="{b64}" width="450"' if b64 else '<img src="" width="0"'
    html = re.sub(r'<img\s[^>]*?src="([^"]*)"[^>]*', _embed, html, flags=re.IGNORECASE)

    # Alle <a>-Varianten bereinigen
    # 1. Externe Links behalten
    html = re.sub(r'<a\s[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>',
                  r'<a href="\1">\2</a>', html, flags=re.DOTALL|re.IGNORECASE)
    # 2. <a> ohne href (Anker-Definitionen) → Inhalt behalten
    html = re.sub(r'<a\b(?![^>]*\bhref\b)[^>]*>(.*?)</a>', r'\1',
                  html, flags=re.DOTALL|re.IGNORECASE)
    # 3. Interne Links (#) → Inhalt behalten
    html = re.sub(r'<a\s[^>]*href="#[^"]*"[^>]*>(.*?)</a>', r'\1',
                  html, flags=re.DOTALL|re.IGNORECASE)
    # 4. Self-closing <a/>
    html = re.sub(r'<a\b[^>]*/>', '', html, flags=re.IGNORECASE)
    # 5. Restliche <a> unwrappen
    html = re.sub(r'<a\b[^>]*>(.*?)</a>', r'\1', html, flags=re.DOTALL|re.IGNORECASE)
    # 6. Verwaiste Tags
    html = re.sub(r'</?a\b[^>]*>', '', html, flags=re.IGNORECASE)

    # id=, name=, class=, style= entfernen
    html = re.sub(r'\s+(?:id|name|class|style|xml:lang|lang|xmlns[^=]*)="[^"]*"', "", html)

    # Unwrap-Tags
    for tag in ("div","span","section","article","aside","nav","header","footer",
                "figure","figcaption","main"):
        html = re.sub(rf"</?{tag}[^>]*>", "", html, flags=re.IGNORECASE)

    # strong/em → b/i
    html = re.sub(r"<(/?)strong>", r"<\1b>", html, flags=re.IGNORECASE)
    html = re.sub(r"<(/?)em>",     r"<\1i>", html, flags=re.IGNORECASE)

    return html.strip()


# ─────────────────────────────────────────────────────────────────────────────
# TOC parsen
# ─────────────────────────────────────────────────────────────────────────────

def _parse_toc(book) -> list[tuple[str, str, int]]:
    """
    Gibt [(title, basename, level), ...] zurück.
    Überspringt Einträge die auf dieselbe Datei zeigen wie der übergeordnete Eintrag.
    """
    import ebooklib
    from ebooklib import epub

    entries: list[tuple[str, str, int]] = []
    seen_files: set[str] = set()

    def _process(item, level: int, parent_file: str | None = None):
        if isinstance(item, epub.Link):
            file_part = item.href.split('#')[0]
            base = os.path.basename(file_part)
            title = (item.title or "").strip()
            if not title or not base:
                return
            # Auf gleicher Seite wie Elterneintrag? → nur erste Erwähnung zeigen
            if base == parent_file and base in seen_files:
                return
            entries.append((title, base, level))
            seen_files.add(base)

        elif isinstance(item, tuple):
            section, children = item
            file_part = (section.href or "").split('#')[0]
            base = os.path.basename(file_part) if file_part else ""
            title = (section.title or "").strip()
            if title and base:
                if not (base == parent_file and base in seen_files):
                    entries.append((title, base, level))
                    seen_files.add(base)
            for child in children:
                _process(child, level + 1, parent_file=base or parent_file)

    for item in book.toc:
        _process(item, level=0)

    return entries


# ─────────────────────────────────────────────────────────────────────────────
# TOC-Seite(n) rendern
# ─────────────────────────────────────────────────────────────────────────────

def _render_toc_pages(pdf, title: str, author: str,
                      toc_entries: list, chapter_pages: dict) -> None:
    """
    Hängt TOC-Seite(n) an das bestehende pdf-Objekt an.
    chapter_pages: { basename → Seitenzahl (1-basiert) }
    Links zeigen auf diese Seitenzahlen – die Seiten müssen bereits im Dokument existieren.
    """
    pdf.add_page()

    # ── Buchtitel + Autor ──
    pdf.set_font("head", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 13, title[:70], align="C", new_x="LMARGIN", new_y="NEXT")
    if author:
        pdf.set_font("head", "", 11)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 8, author[:60], align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # ── Trennlinie ──
    pdf.set_draw_color(200, 185, 160)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(6)

    # ── Überschrift "Inhalt" ──
    pdf.set_font("head", "B", 13)
    pdf.set_text_color(80, 60, 40)
    pdf.cell(0, 9, "Inhalt", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ── Einträge ──
    for entry_title, basename, level in toc_entries:
        target_pg = chapter_pages.get(basename)
        if target_pg is None:
            continue

        # Link anlegen – zeigt auf schon gerenderte Seite
        link_id = pdf.add_link()
        pdf.set_link(link_id, page=target_pg)

        indent   = level * 7          # mm Einzug
        fsize    = 10.5 if level == 0 else 9.5
        weight   = "B"  if level == 0 else ""
        line_h   = 7.5  if level == 0 else 6.5
        gap      = 1.5  if level == 0 else 0.5
        color    = (42, 78, 140) if level == 0 else (70, 100, 160)

        pg_str  = str(target_pg)
        pdf.set_font("body", weight, fsize)
        pg_w    = pdf.get_string_width(pg_str) + 8
        title_w = pdf.epw - indent - pg_w

        # Titel kürzen wenn nötig
        t = entry_title
        while pdf.get_string_width(t) > title_w - 2 and len(t) > 4:
            t = t[:-1]
        t = t.rstrip()
        if len(t) < len(entry_title):
            t += "…"

        # Neue Seite wenn nötig
        if pdf.get_y() > pdf.h - pdf.b_margin - 10:
            pdf.add_page()
            pdf.ln(6)

        pdf.set_text_color(*color)
        pdf.set_x(pdf.l_margin + indent)
        pdf.cell(title_w, line_h, t, link=link_id)

        pdf.set_text_color(120, 120, 120)
        pdf.set_font("body", "", fsize)
        pdf.cell(pg_w, line_h, pg_str, align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0)
        if gap: pdf.ln(gap)

    pdf.set_draw_color(0)


# ─────────────────────────────────────────────────────────────────────────────
# Hauptkonvertierung
# ─────────────────────────────────────────────────────────────────────────────

# Dateien die wir überspringen – diese werden durch unser eigenes TOC ersetzt
TOC_FILE_PATTERNS = re.compile(
    r'(^|/)(?:nav|contents|toc|index|navigation)[\w\-]*\.x?html?$', re.IGNORECASE)


def _is_toc_file(name: str) -> bool:
    return bool(TOC_FILE_PATTERNS.search(name))


def _safe_filename(name: str) -> str:
    """Entfernt Zeichen, die in Dateinamen auf Windows/Linux nicht erlaubt sind."""
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "output"


def _epub_title_as_filename(epub_path: str) -> str:
    """Liest den Buchtitel aus den EPUB-Metadaten; fällt auf Dateinamen zurück."""
    try:
        import ebooklib as _el
        book = _el.read_epub(epub_path, options={"ignore_ncx": False})
        t = (book.title or "").strip()
        return _safe_filename(t) if t else Path(epub_path).stem
    except Exception:
        return Path(epub_path).stem


def convert(epub_path: str, out_path: str, log) -> int:
    try:
        import ebooklib
        from ebooklib import epub as epub_lib
        from fpdf import FPDF
        from fpdf.fonts import FontFace
        from pypdf import PdfWriter, PdfReader
    except ImportError as e:
        raise RuntimeError(f"Fehlende Bibliothek: {e}\n"
                           "Bitte installiere: pip install ebooklib fpdf2 pypdf")

    log(f"Lese {Path(epub_path).name} …")
    book = epub_lib.read_epub(epub_path, options={"ignore_ncx": False})

    title   = book.title or Path(epub_path).stem
    authors = [v for v, _ in book.get_metadata("DC", "creator")]
    author  = ", ".join(authors)
    log(f"Buch: «{title}»" + (f"  —  {author}" if author else ""))

    # Bilder
    images: dict[str, str] = {}
    for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
        ext  = item.get_name().rsplit(".", 1)[-1].lower()
        b64  = f"data:{MIME_MAP.get(ext,'image/jpeg')};base64,{base64.b64encode(item.get_content()).decode()}"
        images[item.get_name()] = b64
        images[os.path.basename(item.get_name())] = b64
    log(f"{len(images)//2} Bilder eingebettet")

    # Spine
    spine_items = [
        book.get_item_with_id(iid)
        for iid, _ in book.spine
        if book.get_item_with_id(iid) and
           book.get_item_with_id(iid).get_type() == ebooklib.ITEM_DOCUMENT
    ]
    content_items = [it for it in spine_items if not _is_toc_file(it.get_name())]
    log(f"{len(content_items)} Kapitel gefunden (von {len(spine_items)} Spine-Einträgen)")

    # Fonts
    body_fonts, head_fonts = _find_fonts()
    if not body_fonts or not head_fonts:
        raise RuntimeError("Keine Schriftarten gefunden (Windows: Times New Roman / Arial erwartet).")
    log(f"Schriftart: {Path(list(body_fonts.values())[0]).stem}")

    # FPDF aufsetzen
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(left=24, top=22, right=20)

    pdf.add_font("body",  style="",   fname=body_fonts[""])
    pdf.add_font("body",  style="B",  fname=body_fonts["B"])
    pdf.add_font("body",  style="I",  fname=body_fonts["I"])
    pdf.add_font("body",  style="BI", fname=body_fonts["BI"])
    pdf.add_font("head",  style="",   fname=head_fonts[""])
    pdf.add_font("head",  style="B",  fname=head_fonts["B"])
    pdf.add_font("head",  style="I",  fname=head_fonts["I"])
    pdf.add_font("head",  style="BI", fname=head_fonts["BI"])

    pdf.set_font("body", size=11)

    tag_styles = {
        "h1": FontFace(family="head", emphasis="B", size_pt=16, color=(25,25,25)),
        "h2": FontFace(family="head", emphasis="B", size_pt=13, color=(25,25,25)),
        "h3": FontFace(family="head", emphasis="B", size_pt=11, color=(25,25,25)),
        "h4": FontFace(family="head", emphasis="B", size_pt=10, color=(25,25,25)),
        "b":  FontFace(family="body", emphasis="B"),
        "strong": FontFace(family="body", emphasis="B"),
        "i":  FontFace(family="body", emphasis="I"),
        "em": FontFace(family="body", emphasis="I"),
    }

    # ── PASS 1: Content rendern ──
    chapter_pages: dict[str, int] = {}  # basename → Seitenzahl (1-basiert)

    for idx, item in enumerate(content_items):
        raw  = item.get_content().decode("utf-8", errors="replace")
        html = _clean_html(raw, item.get_name(), images)
        if not html.strip():
            continue

        pdf.add_page()
        chapter_pages[os.path.basename(item.get_name())] = pdf.page

        try:
            pdf.write_html(html, tag_styles=tag_styles)
        except Exception as e:
            log(f"  ⚠ Kapitel {idx+1} übersprungen: {e}")

        if (idx+1) % 5 == 0 or idx+1 == len(content_items):
            log(f"  Kapitel {idx+1}/{len(content_items)} …")

    content_page_count = pdf.pages_count
    log(f"Kapitel gerendert: {content_page_count} Seiten")

    # ── PASS 2: TOC am Ende rendern (Links zeigen auf bereits existierende Seiten) ──
    log("Erzeuge Inhaltsverzeichnis …")
    toc_entries = _parse_toc(book)
    toc_start_page = pdf.pages_count + 1

    _render_toc_pages(pdf, title, author, toc_entries, chapter_pages)

    toc_page_count = pdf.pages_count - toc_start_page + 1
    log(f"Inhaltsverzeichnis: {toc_page_count} Seite(n), {len(toc_entries)} Einträge")

    # ── pypdf: TOC-Seiten nach vorne schieben ──
    log("Füge Seiten zusammen …")
    src_bytes = io.BytesIO(pdf.output())
    src = PdfReader(src_bytes)
    writer = PdfWriter()

    # TOC zuerst
    for i in range(toc_start_page - 1, src.get_num_pages()):
        writer.add_page(src.pages[i])
    # dann Content
    for i in range(0, toc_start_page - 1):
        writer.add_page(src.pages[i])

    writer.write(out_path)

    final_pages = toc_page_count + content_page_count
    size_kb = Path(out_path).stat().st_size // 1024
    log(f"✓ Fertig — {final_pages} Seiten ({toc_page_count} TOC + {content_page_count} Inhalt), {size_kb} KB")
    log(f"  → {out_path}")
    return final_pages


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

BG, CARD, RED, DARK = "#F5F1EA", "#FFFDF8", "#7E2E32", "#5E2124"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EPUB → PDF")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._epub_path: str | None = None
        self._build_ui()

    def _build_ui(self):
        tk.Label(self, text="EPUB → PDF", bg=BG,
                 font=("Georgia", 22, "bold"), fg="#1a1a1a").pack(pady=(22, 0))
        tk.Label(self, text="Klickbares Inhaltsverzeichnis  ·  Kein Upload  ·  Alles lokal.",
                 bg=BG, font=("Helvetica", 10), fg="#888").pack(pady=(2, 16))

        fc = tk.Frame(self, bg=CARD, highlightthickness=1, highlightbackground="#DDD5BE")
        fc.pack(padx=24, fill="x")
        self._lbl_file = tk.Label(fc, text="Keine Datei gewählt",
                                  bg=CARD, font=("Helvetica", 10), fg="#999",
                                  anchor="w", padx=12, pady=12)
        self._lbl_file.pack(side="left", fill="x", expand=True)
        tk.Button(fc, text="Durchsuchen …", command=self._pick_file,
                  bg=RED, fg="white", relief="flat",
                  font=("Helvetica", 10, "bold"), padx=12, pady=8,
                  cursor="hand2", activebackground=DARK,
                  activeforeground="white").pack(side="right", padx=8, pady=8)

        of = tk.Frame(self, bg=BG)
        of.pack(padx=24, pady=(10, 0), fill="x")
        tk.Label(of, text="Speichern in:", bg=BG,
                 font=("Helvetica", 10), fg="#444").pack(side="left")
        self._var_out = tk.StringVar(value=str(Path.home()))
        tk.Entry(of, textvariable=self._var_out, font=("Helvetica", 10), width=38,
                 relief="flat", highlightthickness=1,
                 highlightbackground="#CCC").pack(side="left", padx=(6,6), ipady=4)
        tk.Button(of, text="…", command=self._pick_outdir, bg="#EEE", relief="flat",
                  font=("Helvetica", 10), padx=8, pady=2,
                  cursor="hand2").pack(side="left")

        self._btn = tk.Button(self, text="In PDF umwandeln", command=self._start,
                              state="disabled", bg=RED, fg="white", relief="flat",
                              font=("Helvetica", 12, "bold"), padx=0, pady=12,
                              cursor="hand2", activebackground=DARK,
                              activeforeground="white", disabledforeground="#CCC")
        self._btn.pack(padx=24, pady=14, fill="x")

        self._pb = ttk.Progressbar(self, mode="indeterminate", length=420)
        self._pb.pack(padx=24, fill="x")

        lf = tk.Frame(self, bg=CARD, highlightthickness=1, highlightbackground="#DDD5BE")
        lf.pack(padx=24, pady=(10, 22), fill="x")
        self._log = tk.Text(lf, height=11, font=("Courier", 9),
                            bg=CARD, fg="#333", relief="flat",
                            state="disabled", padx=10, pady=8, wrap="word")
        sb = tk.Scrollbar(lf, command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        self._log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.update()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}")

    def _pick_file(self):
        p = filedialog.askopenfilename(
            title="EPUB auswählen",
            filetypes=[("EPUB-Dateien", "*.epub"), ("Alle Dateien", "*.*")])
        if p:
            self._epub_path = p
            self._lbl_file.configure(text=Path(p).name, fg="#1a1a1a")
            self._btn.configure(state="normal")
            self._var_out.set(str(Path(p).parent))

    def _pick_outdir(self):
        d = filedialog.askdirectory(title="Zielordner wählen")
        if d:
            self._var_out.set(d)

    def _append_log(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")
        self.update_idletasks()

    def _start(self):
        if not self._epub_path: return
        self._btn.configure(state="disabled", text="Konvertiere …")
        self._log.configure(state="normal"); self._log.delete("1.0","end")
        self._log.configure(state="disabled")
        self._pb.start(12)

        epub_path = self._epub_path
        out_path  = str(Path(self._var_out.get() or Path.home()) /
                        (_epub_title_as_filename(epub_path) + ".pdf"))

        def _worker():
            try:
                convert(epub_path, out_path, self._append_log)
            except Exception as e:
                self._append_log(f"\n❌ Fehler: {e}")
            finally:
                self._pb.stop()
                self._btn.configure(state="normal", text="In PDF umwandeln")

        threading.Thread(target=_worker, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1].endswith(".epub"):
        epub = sys.argv[1]
        out  = sys.argv[2] if len(sys.argv) >= 3 else str(Path(epub).parent / (_epub_title_as_filename(epub) + ".pdf"))
        convert(epub, out, print)
        sys.exit(0)
    App().mainloop()
