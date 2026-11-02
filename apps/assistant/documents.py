"""Lecture et génération de documents pour l'assistant IA.

- extract_text : lit le contenu d'un fichier déposé (pdf, docx, xlsx, csv, txt)
- build_document : produit un .docx ou .pdf à partir d'un texte structuré
- build_table : produit un .xlsx à partir de colonnes + lignes
"""
import io
import re
import uuid
from pathlib import Path

from django.conf import settings

MAX_EXTRACT = 15000  # caractères — protège le contexte de l'IA


# ==================== LECTURE DE FICHIERS DÉPOSÉS ====================

def extract_text(path, filename):
    """Extrait le texte d'un fichier déposé. Lève ValueError (message en français)."""
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    if ext in ('png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'):
        raise ValueError("Je ne sais pas analyser le contenu d'une image — "
                         "uniquement les documents PDF, Word, Excel et texte.")
    if ext == 'pdf':
        from pypdf import PdfReader
        reader = PdfReader(path)
        texte = "\n".join(page.extract_text() or '' for page in reader.pages)
    elif ext == 'docx':
        import docx
        doc = docx.Document(path)
        textes = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                textes.append(' | '.join(c.text.strip() for c in row.cells))
        texte = "\n".join(textes)
    elif ext in ('xlsx', 'xlsm'):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        lignes = []
        for ws in wb.worksheets:
            lignes.append(f"### Feuille : {ws.title}")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    lignes.append(' | '.join('' if v is None else str(v) for v in row))
        texte = "\n".join(lignes)
    elif ext in ('txt', 'csv', 'md'):
        raw = Path(path).read_bytes()
        try:
            texte = raw.decode('utf-8')
        except UnicodeDecodeError:
            texte = raw.decode('latin-1', errors='replace')
    else:
        raise ValueError(f"Format « .{ext} » non pris en charge. "
                         "Envoie un PDF, Word (.docx), Excel (.xlsx), CSV ou texte.")

    texte = texte.strip()
    if not texte:
        raise ValueError("Le fichier semble vide ou illisible (document scanné sans texte ?).")
    return texte[:MAX_EXTRACT]


# ==================== GÉNÉRATION DE DOCUMENTS ====================

def _parse_lignes(contenu):
    """Découpe le texte de l'IA en blocs : (kind, texte) — titre/sous-titre/puce/paragraphe."""
    blocs = []
    for ligne in (contenu or '').splitlines():
        l = ligne.rstrip()
        if not l.strip():
            continue
        if l.startswith('## '):
            blocs.append(('h2', l[3:].strip()))
        elif l.startswith('# '):
            blocs.append(('h1', l[2:].strip()))
        elif l.lstrip().startswith(('- ', '• ')):
            blocs.append(('puce', l.lstrip()[2:].strip()))
        else:
            blocs.append(('p', l.strip()))
    return blocs


def _gras_segments(texte):
    """Découpe « du **gras** ici » en [(texte, bold), ...]."""
    parts = re.split(r'\*\*(.+?)\*\*', texte)
    return [(p, i % 2 == 1) for i, p in enumerate(parts) if p]


def build_document(fmt, titre, contenu):
    """Produit un document Word ou PDF. Retourne (bytes, extension)."""
    fmt = (fmt or '').lower().strip()
    blocs = _parse_lignes(contenu)

    if fmt == 'docx':
        import docx
        from docx.shared import Pt, RGBColor
        doc = docx.Document()
        h = doc.add_heading(titre, level=0)
        for run in h.runs:
            run.font.color.rgb = RGBColor(0x07, 0x59, 0x31)
        for kind, texte in blocs:
            if kind == 'h1':
                doc.add_heading(texte, level=1)
            elif kind == 'h2':
                doc.add_heading(texte, level=2)
            elif kind == 'puce':
                p = doc.add_paragraph(style='List Bullet')
                for seg, bold in _gras_segments(texte):
                    p.add_run(seg).bold = bold
            else:
                p = doc.add_paragraph()
                for seg, bold in _gras_segments(texte):
                    p.add_run(seg).bold = bold
        doc.add_paragraph()
        pied = doc.add_paragraph(f"{settings.ASSISTANT_DOC_FOOTER}")
        pied.runs[0].font.size = Pt(8)
        pied.runs[0].font.color.rgb = RGBColor(0x88, 0x88, 0x88)
        buf = io.BytesIO()
        doc.save(buf)
        return buf.getvalue(), 'docx'

    if fmt == 'pdf':
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                                topMargin=16 * mm, bottomMargin=16 * mm)
        st_titre = ParagraphStyle('t', fontName='Helvetica-Bold', fontSize=16,
                                  textColor='#075931', spaceAfter=8)
        st_h1 = ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=13,
                               textColor='#018945', spaceBefore=8, spaceAfter=4)
        st_h2 = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=11,
                               textColor='#018945', spaceBefore=6, spaceAfter=3)
        st_p = ParagraphStyle('p', fontName='Helvetica', fontSize=10, leading=14,
                              spaceAfter=4)
        st_pied = ParagraphStyle('f', fontName='Helvetica-Oblique', fontSize=7.5,
                                 textColor='#999999', spaceBefore=14)
        elements = [Paragraph(titre, st_titre)]
        for kind, texte in blocs:
            html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', texte)
            if kind == 'h1':
                elements.append(Paragraph(html, st_h1))
            elif kind == 'h2':
                elements.append(Paragraph(html, st_h2))
            elif kind == 'puce':
                elements.append(Paragraph('• ' + html, st_p))
            else:
                elements.append(Paragraph(html, st_p))
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(settings.ASSISTANT_DOC_FOOTER, st_pied))
        doc.build(elements)
        return buf.getvalue(), 'pdf'

    raise ValueError("Format de document inconnu : choisis « docx » ou « pdf ».")


def build_table(titre, colonnes, lignes):
    """Produit un classeur Excel. Retourne (bytes, 'xlsx')."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    vert = PatternFill('solid', fgColor='018945')
    clair = PatternFill('solid', fgColor='E8F5E9')
    bord = Border(*[Side(style='thin', color='D1D5DB')] * 4)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Tableau'
    ws.sheet_view.showGridLines = False

    ncol = max(len(colonnes), 1)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    c = ws.cell(row=1, column=1, value=titre)
    c.font = Font(bold=True, size=13, color='075931')

    for i, col in enumerate(colonnes, 1):
        c = ws.cell(row=2, column=i, value=str(col))
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = vert
        c.border = bord
        c.alignment = Alignment(horizontal='center', vertical='center')

    for r, ligne in enumerate(lignes, 3):
        for i in range(1, ncol + 1):
            val = ligne[i - 1] if i - 1 < len(ligne) else ''
            c = ws.cell(row=r, column=i, value=val)
            c.border = bord
            if r % 2:
                c.fill = clair

    for i in range(1, ncol + 1):
        lettre = get_column_letter(i)
        longest = max([len(str(colonnes[i - 1]))]
                      + [len(str(l[i - 1])) for l in lignes if i - 1 < len(l)] + [10])
        ws.column_dimensions[lettre].width = min(longest + 4, 45)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue(), 'xlsx'


def save_generated(data, ext, titre):
    """Écrit le fichier généré dans MEDIA_ROOT/assistant/files/ → chemin relatif média."""
    safe = re.sub(r'[^\w\- ]', '', (titre or 'document'))[:40].strip().replace(' ', '_')
    rel = f"assistant/files/{safe or 'document'}_{uuid.uuid4().hex[:8]}.{ext}"
    dest = Path(settings.MEDIA_ROOT) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return rel
