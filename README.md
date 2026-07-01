# bookbinder — EPUB to PDF converter

Convert EPUB ebooks to PDF, locally, with a clickable table of contents.

```bash
pip install ebooklib fpdf2 pypdf
python bookbinder.py
```

No Calibre. No GTK. No uploads. Just Python.

---

## Why another EPUB to PDF tool?

Most converters either require a full Calibre installation, a GTK runtime (painful on Windows), or send your files to a cloud service. Bookbinder needs nothing except Python and three pip packages — and it's the only one I've found that generates a **clickable table of contents** where every entry links directly to the right page.

The TOC trick: chapters are rendered first (so page numbers are known), the TOC is appended at the end with working internal links, then `pypdf` moves those pages to the front. PDF links reference page objects rather than page numbers, so they survive the reorder intact.

---

## Installation

```bash
pip install ebooklib fpdf2 pypdf
```

Python 3.10+ required.

---

## Usage

**GUI** — drag and drop or browse for your EPUB:
```bash
python bookbinder.py
```

**Command line:**
```bash
python bookbinder.py book.epub
python bookbinder.py book.epub output.pdf
```

The PDF lands next to the original EPUB unless you specify a path.

---

## Fonts

**Windows** — Times New Roman and Arial are used automatically. No setup.

**Linux / macOS** — DejaVu or Liberation fonts are picked up from the system. Most distros include them; install with `apt install fonts-dejavu` or `brew install font-dejavu` if not.

---

## Package as a standalone .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed bookbinder.py
```

The result in `dist/bookbinder.exe` runs without Python installed.

---

## Known limitations

- Layout is re-typeset with clean defaults rather than reproducing the original EPUB styles exactly. Many EPUB stylesheets assume a reflowable e-reader and break on fixed PDF pages — this is the deliberate trade-off.
- Complex tables and mathematical formulas may not render perfectly.
- TOC links point to the chapter's first page. Sub-section anchors within a chapter are not resolved.
- Tested on Windows 10/11 (Python 3.13) and Ubuntu 24 (Python 3.12).

---

## Dependencies

| Package | Role |
|---|---|
| `ebooklib` | Reads the EPUB |
| `fpdf2` | Generates the PDF |
| `pypdf` | Reorders pages to put the TOC first |

---

## License

MIT
