"""
Generate test PDF fixtures for pipeline and OCR tests.

Creates:
1. image_only_manifesto.pdf — A French manifesto rendered as images (no extractable text)
2. image_only_poster.pdf   — An election poster rendered as an image
3. mixed_pdf.pdf           — Pages 1,3 are images; page 2 has real text
4. text_manifesto.pdf      — Normal text-based PDF (baseline)
5. scanned_handwritten.pdf — Simulated handwritten/low-quality scan

Run once:
    poetry run python tests/fixtures/generate_pdf_fixtures.py
"""

import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path(__file__).parent

# French political text samples for rendering
MANIFESTO_TEXT = """PROGRAMME MUNICIPAL 2026
Liste « Ensemble pour Notre Ville »
Tête de liste : Marie-Claire Dupont

1. LOGEMENT
Construction de 500 logements sociaux d'ici 2030.
Rénovation thermique de 1 200 bâtiments publics.
Encadrement des loyers dans les quartiers tendus.

2. TRANSPORT
Création de 3 nouvelles lignes de bus électriques.
Extension du réseau de pistes cyclables (+40 km).
Gratuité des transports pour les moins de 18 ans.

3. ENVIRONNEMENT
Plantation de 10 000 arbres en zones urbaines.
Zéro artificialisation nette des sols.
Budget participatif vert de 2 millions d'euros.

4. ÉDUCATION
Cantine bio et locale dans toutes les écoles.
Ouverture de 2 crèches municipales.
Soutien scolaire gratuit dans chaque quartier."""

POSTER_TEXT = """ÉLECTIONS MUNICIPALES 2026
DIMANCHE 15 MARS

VOTEZ
Marie-Claire DUPONT
Tête de liste

ENSEMBLE POUR NOTRE VILLE

✓ 500 logements sociaux
✓ Transports gratuits -18 ans
✓ 10 000 arbres plantés
✓ Cantine bio dans les écoles

www.ensemble-notre-ville.fr
@ensemblenotrevile"""

SHORT_TEXT = """Déclaration de politique générale
Le conseil municipal s'engage à améliorer
la qualité de vie des habitants."""

HANDWRITTEN_STYLE_TEXT = """Chers citoyens,

Je m'engage personnellement à:
- Réduire les impôts locaux de 5%
- Ouvrir un centre médical
- Rénover le stade municipal
- Créer 200 emplois locaux

Avec tout mon dévouement,
Jean-Pierre Martin
Candidat indépendant"""


def _get_font(size: int = 24):
    """Get a font, falling back to default if needed."""
    # Try common system fonts
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Geneva.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _render_text_to_image(
    text: str,
    width: int = 1200,
    height: int = 1600,
    font_size: int = 24,
    bg_color: str = "white",
    text_color: str = "black",
    noise: bool = False,
) -> Image.Image:
    """Render text onto an image, simulating a scanned document."""
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    font = _get_font(font_size)

    # Draw text with word wrapping
    margin = 80
    y = margin
    for line in text.split("\n"):
        if not line.strip():
            y += font_size
            continue
        # Simple word wrap
        words = line.split()
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] > width - 2 * margin:
                draw.text((margin, y), current_line, fill=text_color, font=font)
                y += font_size + 8
                current_line = word
            else:
                current_line = test_line
        if current_line:
            draw.text((margin, y), current_line, fill=text_color, font=font)
            y += font_size + 8

    if noise:
        # Add slight grey noise to simulate scan artifacts
        import random
        pixels = img.load()
        for _ in range(width * height // 50):
            x = random.randint(0, width - 1)
            ry = random.randint(0, height - 1)
            grey = random.randint(180, 220)
            pixels[x, ry] = (grey, grey, grey)

    return img


def _images_to_pdf(images: list[Image.Image]) -> bytes:
    """Convert a list of PIL images to a PDF bytes object."""
    output = io.BytesIO()
    if len(images) == 1:
        images[0].save(output, format="PDF")
    else:
        images[0].save(output, format="PDF", save_all=True, append_images=images[1:])
    return output.getvalue()


def generate_image_only_manifesto() -> bytes:
    """Generate a multi-page image-only manifesto PDF."""
    lines = MANIFESTO_TEXT.split("\n")
    mid = len(lines) // 2
    page1_text = "\n".join(lines[:mid])
    page2_text = "\n".join(lines[mid:])

    img1 = _render_text_to_image(page1_text, font_size=26)
    img2 = _render_text_to_image(page2_text, font_size=26)
    return _images_to_pdf([img1, img2])


def generate_image_only_poster() -> bytes:
    """Generate a single-page election poster as an image PDF."""
    img = _render_text_to_image(
        POSTER_TEXT,
        width=900,
        height=1400,
        font_size=30,
    )
    return _images_to_pdf([img])


def generate_mixed_pdf() -> bytes:
    """Generate a PDF where pages 1 and 3 are images, page 2 is real text.

    This tests the OCR fallback threshold — total pypdf text from page 2
    may be under MIN_TEXT_FOR_OCR_FALLBACK.
    """
    from pypdf import PdfWriter

    writer = PdfWriter()

    # Page 1: image
    img1 = _render_text_to_image(MANIFESTO_TEXT.split("\n\n")[0], height=800)
    img1_pdf = io.BytesIO()
    img1.save(img1_pdf, format="PDF")
    img1_pdf.seek(0)
    from pypdf import PdfReader
    reader1 = PdfReader(img1_pdf)
    writer.add_page(reader1.pages[0])

    # Page 2: real text via reportlab (if available) or a minimal text PDF
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 12)
        y = 750
        for line in SHORT_TEXT.split("\n"):
            c.drawString(72, y, line)
            y -= 18
        c.showPage()
        c.save()
        buf.seek(0)
        reader2 = PdfReader(buf)
        writer.add_page(reader2.pages[0])
    except ImportError:
        # Fallback: just add another image page
        img2 = _render_text_to_image(SHORT_TEXT, height=800)
        img2_pdf = io.BytesIO()
        img2.save(img2_pdf, format="PDF")
        img2_pdf.seek(0)
        reader2 = PdfReader(img2_pdf)
        writer.add_page(reader2.pages[0])

    # Page 3: image
    img3 = _render_text_to_image("Contact: mairie@ville.fr\nTél: 01 23 45 67 89", height=800)
    img3_pdf = io.BytesIO()
    img3.save(img3_pdf, format="PDF")
    img3_pdf.seek(0)
    reader3 = PdfReader(img3_pdf)
    writer.add_page(reader3.pages[0])

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def generate_text_manifesto() -> bytes:
    """Generate a normal text-based PDF (baseline for comparison)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        c.setFont("Helvetica", 11)
        y = 780
        for line in MANIFESTO_TEXT.split("\n"):
            if y < 60:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = 780
            c.drawString(60, y, line)
            y -= 16
        c.showPage()
        c.save()
        buf.seek(0)
        return buf.getvalue()
    except ImportError:
        # Without reportlab, create a minimal PDF with text
        # This is a bare-minimum valid PDF
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        for line in MANIFESTO_TEXT.split("\n"):
            pdf.cell(0, 8, line, ln=True)
        return pdf.output()


def generate_scanned_handwritten() -> bytes:
    """Generate a 'handwritten' style image PDF with scan noise."""
    img = _render_text_to_image(
        HANDWRITTEN_STYLE_TEXT,
        width=1000,
        height=1400,
        font_size=28,
        bg_color="#f5f0e8",  # Yellowish paper
        text_color="#1a1a2e",  # Dark blue ink
        noise=True,
    )
    return _images_to_pdf([img])


def main():
    """Generate all fixtures and write to disk."""
    fixtures = {
        "image_only_manifesto.pdf": generate_image_only_manifesto,
        "image_only_poster.pdf": generate_image_only_poster,
        "mixed_pdf.pdf": generate_mixed_pdf,
        "scanned_handwritten.pdf": generate_scanned_handwritten,
    }

    # text_manifesto needs reportlab or fpdf — generate separately
    try:
        fixtures["text_manifesto.pdf"] = generate_text_manifesto
    except Exception as e:
        print(f"Skipping text_manifesto.pdf (needs reportlab or fpdf): {e}")

    for name, gen_fn in fixtures.items():
        path = FIXTURES_DIR / name
        try:
            data = gen_fn()
            path.write_bytes(data)
            print(f"Generated {name} ({len(data):,} bytes)")
        except Exception as e:
            print(f"FAILED {name}: {e}")

    print(f"\nFixtures written to: {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
