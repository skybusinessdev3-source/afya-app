from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from apps.settings_app.models import CenterConfig

BRAND = colors.HexColor('#00ad53')
BRAND_DARK = colors.HexColor('#075931')
GRAY = colors.HexColor('#6b7280')

XL_GREEN = PatternFill('solid', fgColor='00AD53')
XL_LIGHT = PatternFill('solid', fgColor='EAFFF3')
XL_THIN = Side(style='thin', color='D1D5DB')


def _center_name():
    config = CenterConfig.objects.first()
    return config.name if config else 'CRF-MK'


# ================= PDF =================

def build_pdf(vue, report):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    styles = {
        'title': ParagraphStyle('t', fontSize=16, textColor=BRAND_DARK, fontName='Helvetica-Bold', spaceAfter=4),
        'sub': ParagraphStyle('s', fontSize=10, textColor=GRAY, spaceAfter=10),
        'h2': ParagraphStyle('h2', fontSize=12, textColor=BRAND_DARK, fontName='Helvetica-Bold',
                             spaceBefore=10, spaceAfter=4),
        'body': ParagraphStyle('b', fontSize=10, leading=14),
    }

    el = []
    el.append(Paragraph(_center_name(), styles['title']))
    titre = {'jour': 'RAPPORT JOURNALIER', 'mois': 'RAPPORT MENSUEL', 'annee': 'RAPPORT ANNUEL'}[vue]
    el.append(Paragraph(f"{titre} — {report['label']}", styles['sub']))

    # --- Ventilation des recettes (devises en colonnes séparées) ---
    el.append(Paragraph('Ventilation des recettes', styles['h2']))
    rows = [['Module', 'Montant']] if vue != 'annee' else [['Mois', 'Patients', 'Séances', 'Perçus', 'Dépenses']]
    if vue != 'annee':
        for label, key in [('Centre (séances/consultations)', 'centre'), ('Médecine générale', 'med_gen'),
                           ('Médecine manuelle', 'med_man'), ('Pharmacie', 'pharmacy'),
                           ('Laboratoire', 'laboratory'), ('Soins à domicile', 'home_care')]:
            rows.append([label, report[key]])
        rows.append(['TOTAL PERÇUS', report['total_percus']])
    else:
        for m in report['months']:
            rows.append([m['name'], str(m['patients']), str(m['sessions']), m['percus'], m['depenses']])
        rows.append(['TOTAL', str(report['patients_total']), '', report['total_percus'], report['total_depenses']])

    t = Table(rows, hAlign='LEFT', colWidths=None)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BRAND),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dcfce7')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    el.append(t)

    if vue == 'jour':
        el.append(Paragraph('Patients et mouvements', styles['h2']))
        for line in report['patients_lines']:
            el.append(Paragraph(line, styles['body']))
        el.append(Paragraph('Dépenses', styles['h2']))
        for line in (report['expense_lines'] or ['—']):
            el.append(Paragraph(line.replace('*', '').replace('_', ''), styles['body']))

    # --- Solde encadré ---
    el.append(Spacer(1, 8))
    solde = Table([[f"SOLDE NET : {report['solde']}"], ],
                  colWidths=[170 * mm], rowHeights=[12 * mm])
    solde.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BRAND_DARK),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    el.append(solde)

    doc.build(el)
    buf.seek(0)
    return buf.read()


# ================= EXCEL =================

def build_excel(vue, report):
    wb = Workbook()
    ws = wb.active
    ws.title = f"Rapport {report['label']}".replace('/', '-').replace('\\', '-')[:31]
    ws.sheet_view.showGridLines = False

    def style_header(cell):
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = XL_GREEN
        cell.alignment = Alignment(horizontal='center')

    def put(row, col, value, bold=False, fill=None, align='left'):
        c = ws.cell(row=row, column=col, value=value)
        c.font = Font(bold=bold)
        c.border = Border(top=XL_THIN, bottom=XL_THIN, left=XL_THIN, right=XL_THIN)
        if fill:
            c.fill = fill
        c.alignment = Alignment(horizontal=align, vertical='center')
        return c

    # Titre
    ws.merge_cells('A1:E1')
    put(1, 1, _center_name(), bold=True).font = Font(bold=True, size=14, color='075931')
    titre = {'jour': 'RAPPORT JOURNALIER', 'mois': 'RAPPORT MENSUEL', 'annee': 'RAPPORT ANNUEL'}[vue]
    ws.merge_cells('A2:E2')
    put(2, 1, f"{titre} — {report['label']}", bold=True)
    row = 4

    if vue != 'annee':
        put(row, 1, 'VENTILATION DES RECETTES', bold=True, fill=XL_LIGHT); row += 1
        put(row, 1, 'Module', bold=True); put(row, 2, 'Montant', bold=True)
        style_header(ws.cell(row=row, column=1)); style_header(ws.cell(row=row, column=2))
        row += 1
        for label, key in [('Centre (séances/consultations)', 'centre'), ('Médecine générale', 'med_gen'),
                           ('Médecine manuelle', 'med_man'), ('Pharmacie', 'pharmacy'),
                           ('Laboratoire', 'laboratory'), ('Soins à domicile', 'home_care')]:
            put(row, 1, label); put(row, 2, report[key]); row += 1
        put(row, 1, 'TOTAL PERÇUS', bold=True, fill=XL_LIGHT)
        put(row, 2, report['total_percus'], bold=True, fill=XL_LIGHT); row += 2

        put(row, 1, 'DÉPENSES', bold=True, fill=XL_LIGHT); row += 1
        put(row, 1, 'Libellé', bold=True); put(row, 2, 'Montant', bold=True)
        style_header(ws.cell(row=row, column=1)); style_header(ws.cell(row=row, column=2))
        row += 1
        if report['expense_lines']:
            for line in report['expense_lines']:
                # ligne type "* X : _Y_" → libellé / montant
                clean = line.replace('*', '').replace('_', '').strip()
                libelle, _, montant = clean.partition(' : ')
                put(row, 1, libelle); put(row, 2, montant); row += 1
        else:
            put(row, 1, '—'); put(row, 2, '0'); row += 1
        put(row, 1, 'TOTAL DÉPENSES', bold=True, fill=XL_LIGHT)
        put(row, 2, report['total_depenses'], bold=True, fill=XL_LIGHT); row += 2
    else:
        put(row, 1, 'DÉTAIL PAR MOIS', bold=True, fill=XL_LIGHT); row += 1
        headers = ['Mois', 'Patients', 'Séances', 'Perçus', 'Dépenses']
        for i, h in enumerate(headers, 1):
            put(row, i, h, bold=True)
            style_header(ws.cell(row=row, column=i))
        row += 1
        for m in report['months']:
            put(row, 1, m['name']); put(row, 2, m['patients'], align='center')
            put(row, 3, m['sessions'], align='center')
            put(row, 4, m['percus']); put(row, 5, m['depenses'])
            row += 1
        put(row, 1, 'TOTAL', bold=True, fill=XL_LIGHT)
        put(row, 2, report['patients_total'], bold=True, fill=XL_LIGHT, align='center')
        put(row, 3, '', fill=XL_LIGHT)
        put(row, 4, report['total_percus'], bold=True, fill=XL_LIGHT)
        put(row, 5, report['total_depenses'], bold=True, fill=XL_LIGHT)
        row += 2

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    c = put(row, 1, f"SOLDE NET : {report['solde']}", bold=True, fill=XL_GREEN, align='center')
    c.font = Font(bold=True, color='FFFFFF', size=12)
    ws.row_dimensions[row].height = 24

    # Largeurs de colonnes
    for i, w in enumerate([38, 18, 12, 22, 22], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()

# ================= ENTREPRISES (annexe mensuelle — ex : LTJ) =================

def build_company_excel(report):
    """Excel calqué sur « ANNEXE LTJ JUILLET 2026.xlsx » :
    Noms | Pharmacie & Autres | Nbre Préscrit | Effectué | Restant | Cout | Date | Observation.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = f"ANNEXE {report['label']}"[:31]
    ws.sheet_view.showGridLines = False

    thin = Border(top=XL_THIN, bottom=XL_THIN, left=XL_THIN, right=XL_THIN)

    def put(row, col, value, bold=False, fill=None, align='left'):
        c = ws.cell(row=row, column=col, value=value)
        c.font = Font(bold=bold)
        c.border = thin
        if fill:
            c.fill = fill
        c.alignment = Alignment(horizontal=align, vertical='center')
        return c

    company = report['company']
    # Titre
    ws.merge_cells('A1:H1')
    c = put(1, 1, f"PATIENTS {company.name.upper()} {report['mois_nom']} {report['year']}",
            bold=True, align='center')
    c.font = Font(bold=True, size=14, color='075931')

    # En-têtes
    headers = ['Noms Patients', 'Pharmacie & Autres', 'Nbre Préscrit', 'Effectué',
               'Restant', 'Cout', 'Date', 'Observation']
    for i, h in enumerate(headers, 1):
        put(2, i, h, bold=True, align='center')
        ws.cell(row=2, column=i).font = Font(bold=True, color='FFFFFF')
        ws.cell(row=2, column=i).fill = XL_GREEN

    # Lignes patients
    row = 3
    for n, r in enumerate(report['rows'], 1):
        put(row, 1, f"{n}. {r['patient'].full_name}")
        put(row, 2, float(r['pharmacie']) if r['pharmacie'] else '', align='center')
        put(row, 3, r['prescrit'], align='center')
        put(row, 4, r['effectue'], align='center')
        put(row, 5, r['restant'], align='center')
        put(row, 6, r['cout_txt'], align='center')
        put(row, 7, r['date_txt'], align='center')
        put(row, 8, r['observation'])
        row += 1

    # TOTAL
    tot = report['tot']
    put(row, 1, 'TOTAL', bold=True, fill=XL_LIGHT)
    put(row, 2, float(tot['pharmacie']), bold=True, fill=XL_LIGHT, align='center')
    put(row, 3, tot['prescrit'], bold=True, fill=XL_LIGHT, align='center')
    put(row, 4, tot['effectue'], bold=True, fill=XL_LIGHT, align='center')
    put(row, 5, tot['restant'], bold=True, fill=XL_LIGHT, align='center')
    put(row, 6, float(tot['cout']), bold=True, fill=XL_LIGHT, align='center')
    put(row, 7, '', fill=XL_LIGHT); put(row, 8, '', fill=XL_LIGHT)
    row += 1

    # TOTAL GENERAL + clôture
    put(row, 1, 'TOTAL  GENERAL', bold=True)
    put(row, 6, float(report['total_general']), bold=True, align='center')
    put(row, 8, report['cloture'], bold=True)

    for i, w in enumerate([26, 17, 13, 10, 9, 14, 15, 30], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
