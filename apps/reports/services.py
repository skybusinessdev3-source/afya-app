from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from apps.appointments.models import Appointment
from apps.centre.models import Session
from apps.finance.models import Expense, Payment
from apps.laboratory.models import LaboratoryRecord
from apps.home_care.models import HomeCareService
from apps.medicine.models import MedicineRecord
from apps.pharmacy.models import PharmacySale


# ================= OUTILS =================

def _sums_by_currency(queryset):
    """Jamais mélanger les devises : {'USD': x, 'FC': y}"""
    usd = queryset.filter(currency_original='USD').aggregate(t=Sum('amount_original'))['t'] or 0
    fc = queryset.filter(currency_original='FC').aggregate(t=Sum('amount_original'))['t'] or 0
    return {'USD': usd, 'FC': fc}


def _fmt(amounts):
    parts = []
    if amounts['USD']:
        parts.append(f"{amounts['USD']}$")
    if amounts['FC']:
        parts.append(f"{amounts['FC']:,.0f}fc".replace(',', ' '))
    return ' + '.join(parts) if parts else '0'


def _categorize(payment):
    inv = payment.invoice
    if inv is None:
        return 'centre'
    if inv.lab_records.exists():
        return 'laboratoire'
    if inv.home_care_services.exists():
        return 'domicile'
    if inv.label.startswith('Pharmacie'):
        return 'pharmacie'
    med = inv.medicine_records.first()
    if med is not None:
        return 'medecine_manuelle' if med.category.startswith('MANUAL') else 'medecine_generale'
    return 'centre'


def _ventilation(payments):
    vent = defaultdict(lambda: {'USD': 0, 'FC': 0})
    for p in payments.select_related('invoice'):
        vent[_categorize(p)][p.currency_original] += p.amount_original
    return vent


# ================= AVANCES SÉANCES =================
# (x/y) dans le rapport = x séances EFFECTUÉES / y séances PAYÉES (avance),
# et non « y prescrites » : tout le monde ne paie pas de la même manière.
# prix_séance = montant dû (centre) ÷ séances prescrites → y = payé ÷ prix_séance.

def _factures_centre(patient_ids):
    """Montants dus/payés (USD) des factures 'centre' de chaque patient :
    on exclut pharmacie, labo, médecine et soins à domicile — seules les
    séances/consultations comptent pour l'avance en séances."""
    from apps.finance.models import Invoice, Payment
    res = {pid: {'due': Decimal('0'), 'paid': Decimal('0')} for pid in patient_ids}
    if not patient_ids:
        return res
    invoices = (Invoice.objects
                .filter(patient_id__in=patient_ids)
                .exclude(status=Invoice.Status.CANCELLED)
                .prefetch_related('lab_records', 'home_care_services',
                                  'medicine_records', 'payments'))
    for inv in invoices:
        if (inv.label.startswith('Pharmacie') or inv.lab_records.exists()
                or inv.home_care_services.exists() or inv.medicine_records.exists()):
            continue  # pas une facture de séances/consultations
        res[inv.patient_id]['due'] += inv.amount_usd
        res[inv.patient_id]['paid'] += sum(
            p.amount_usd for p in inv.payments.all()
            if p.status == Payment.Status.VALID)
    return res


def _seances_payees(due, paid, prescribed):
    """Nombre de séances payées (avance). None si non calculable
    (pas de séances prescrites ou pas de montant dû au centre)."""
    if not prescribed or prescribed <= 0 or due <= 0:
        return None
    prix = due / prescribed
    if prix <= 0:
        return None
    return (paid / prix).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)


def _fmt_seances(nb):
    """3.0 → '3' ; 2.5 → '2.5'."""
    if nb is None:
        return None
    return _fmt_nombre(nb)


def _fmt_nombre(d):
    """Decimal → texte lisible : 20 (jamais '2E+1'), 12.5 (jamais '12.50')."""
    txt = format(d, 'f')
    if '.' in txt:
        txt = txt.rstrip('0').rstrip('.')
    return txt


# ================= JOURNALIER =================

def daily_report(d):
    sessions = Session.objects.filter(date=d).select_related('patient', 'patient__company', 'service')
    payments = Payment.objects.filter(date=d, status=Payment.Status.VALID)
    expenses = Expense.objects.filter(date=d)

    vent = _ventilation(payments)
    # Avances : factures 'centre' de tous les patients présents ce jour
    pids = {s.patient_id for s in sessions}
    fin = _factures_centre(pids)

    def _seances_label(patient):
        # Entreprise « créances » (ex : LTJ) : le patient ne paie pas → prescrites
        if patient.company_id and patient.company and patient.company.facturation_entreprise:
            return f"_{patient.sessions_done}/{patient.sessions_prescribed}_"
        payees = _seances_payees(fin[patient.id]['due'], fin[patient.id]['paid'],
                                 patient.sessions_prescribed)
        total = _fmt_seances(payees)
        if total is None:                       # pas de tarif calculable → prescrites
            total = patient.sessions_prescribed
        return f"_{patient.sessions_done}/{total}_"

    patients_lines = []
    for i, s in enumerate(sessions, 1):
        pays = [p for p in payments if p.invoice and p.invoice.patient_id == s.patient_id]
        amounts = {'USD': sum(p.amount_original for p in pays if p.currency_original == 'USD'),
                   'FC': sum(p.amount_original for p in pays if p.currency_original == 'FC')}
        money = f" : {_fmt(amounts)}" if (amounts['USD'] or amounts['FC']) else ""
        seances = _seances_label(s.patient)
        patients_lines.append(f"{i}. {s.patient.full_name} ({seances}{money})")

    # --- Patients des AUTRES services (labo, médecine, domicile, pharmacie) ---
    # Pas de séance au centre ce jour → ils doivent quand même apparaître au rapport.
    seen = {s.patient_id for s in sessions}
    extra = {}

    def _add_extra(patient, tag):
        if patient is None or patient.id in seen:
            return
        extra.setdefault(patient.id, {'patient': patient, 'tags': set()})['tags'].add(tag)

    for r in LaboratoryRecord.objects.filter(date=d).select_related('patient'):
        _add_extra(r.patient, 'Labo')
    for r in MedicineRecord.objects.filter(date=d).select_related('patient'):
        _add_extra(r.patient, 'Médecine')
    for r in HomeCareService.objects.filter(date=d).select_related('patient'):
        _add_extra(r.patient, 'Domicile')
    for s in PharmacySale.objects.filter(date=d).select_related('patient'):
        _add_extra(s.patient, 'Pharmacie')

    i = len(patients_lines)
    for pid, info in extra.items():
        pays = [p for p in payments if p.invoice and p.invoice.patient_id == pid]
        amounts = {'USD': sum(p.amount_original for p in pays if p.currency_original == 'USD'),
                   'FC': sum(p.amount_original for p in pays if p.currency_original == 'FC')}
        money = f" : {_fmt(amounts)}" if (amounts['USD'] or amounts['FC']) else ""
        i += 1
        patients_lines.append(f"{i}. {info['patient'].full_name} "
                              f"({'/'.join(sorted(info['tags']))}{money})")

    exp_total = _sums_by_currency(expenses)
    total = _sums_by_currency(payments)

    return {
        'label': d.strftime('%d/%m/%Y'),
        'patients_count': len(seen) + len(extra),
        'sessions_count': sessions.count(),
        'patients_lines': patients_lines,
        'pharmacy': _fmt(vent['pharmacie']),
        'laboratory': _fmt(vent['laboratoire']),
        'home_care': _fmt(vent['domicile']),
        'centre': _fmt(vent['centre']),
        'med_gen': _fmt(vent['medecine_generale']),
        'med_man': _fmt(vent['medecine_manuelle']),
        'total_percus': _fmt(total),
        'expense_lines': [f"* {e.label} : _{e.amount_original} {e.currency_original}_" for e in expenses],
        'total_depenses': _fmt(exp_total),
        'solde': _fmt({'USD': total['USD'] - exp_total['USD'], 'FC': total['FC'] - exp_total['FC']}),
        'extra': f"Pharmacie : {PharmacySale.objects.filter(date=d).count()} vente(s) · "
                 f"Labo : {LaboratoryRecord.objects.filter(date=d).count()} examen(s)",
    }


def whatsapp_daily(r):
    lines = [
        f"*RAPPORT DU {r['label']}*", "",
        "Bonsoir à tous,", "",
        "J'espère que vous vous portez bien. C'est avec plaisir que je vous présente le rapport d'activités du jour.", "",
        f"Le CRF-MK a fonctionné normalement aujourd'hui en enregistrant {r['patients_count']} patients.", "",
        "*LISTE DES PATIENTS ET MOUVEMENTS :*",
        *(r['patients_lines'] or ["—"]), "",
        "*VENTILATION DES RECETTES :*",
        f"*CENTRE (séances/consultations)* : _{r['centre']}_",
        f"*MÉDECINE GÉNÉRALE* : _{r['med_gen']}_",
        f"*MÉDECINE MANUELLE* : _{r['med_man']}_",
        f"*PHARMACIE* : _{r['pharmacy']}_",
        f"*LABORATOIRE* : _{r['laboratory']}_",
        f"*SOINS À DOMICILE* : _{r['home_care']}_",
        f"*TOTAL PERÇUS* : _{r['total_percus']}_", "",
        "*DÉPENSES DU JOUR :*",
        *(r['expense_lines'] or ["—"]),
        f"*Total Dépenses :* _{r['total_depenses']}_", "",
        "*SOLDE / RESTE EN MAIN :*",
        f"_{r['solde']}_", "",
        "*Cordialement* 🙌",
    ]
    return '\n'.join(lines)


# ================= MENSUEL =================

def monthly_report(year, month):
    payments = Payment.objects.filter(date__year=year, date__month=month, status='VALID')
    expenses = Expense.objects.filter(date__year=year, date__month=month)
    sessions = Session.objects.filter(date__year=year, date__month=month)

    vent = _ventilation(payments)
    exp_total = _sums_by_currency(expenses)
    total = _sums_by_currency(payments)
    from django.utils import timezone
    import calendar
    month_name = calendar.month_name[month] if hasattr(calendar, 'month_name') else str(month)
    # noms français :
    MOIS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
            'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

    return {
        'label': f"{MOIS[month]} {year}",
        'patients_count': sessions.values('patient').distinct().count(),
        'sessions_count': sessions.count(),
        'jours_actifs': sessions.values('date').distinct().count(),
        'pharmacy': _fmt(vent['pharmacie']),
        'laboratory': _fmt(vent['laboratoire']),
        'home_care': _fmt(vent['domicile']),
        'centre': _fmt(vent['centre']),
        'med_gen': _fmt(vent['medecine_generale']),
        'med_man': _fmt(vent['medecine_manuelle']),
        'total_percus': _fmt(total),
        'med_gen_count': MedicineRecord.objects.filter(
            date__year=year, date__month=month).exclude(category__startswith='MANUAL').count(),
        'med_man_count': MedicineRecord.objects.filter(
            date__year=year, date__month=month, category__startswith='MANUAL').count(),
        'expenses_count': expenses.count(),
        'total_depenses': _fmt(exp_total),
        'solde': _fmt({'USD': total['USD'] - exp_total['USD'], 'FC': total['FC'] - exp_total['FC']}),
        'lab_count': LaboratoryRecord.objects.filter(date__year=year, date__month=month).count(),
        'sales_count': PharmacySale.objects.filter(date__year=year, date__month=month).count(),
        'home_care_count': HomeCareService.objects.filter(date__year=year, date__month=month).count(),
    }


def whatsapp_monthly(r):
    lines = [
        f"*RAPPORT MENSUEL — {r['label']}*", "",
        "Bonsoir à tous,", "",
        "Voici le bilan du mois.", "",
        f"*ACTIVITÉ* : {r['patients_count']} patients · {r['sessions_count']} séances · {r['jours_actifs']} jours d'activité", "",
        "*VENTILATION DES RECETTES :*",
        f"*CENTRE (séances/consultations)* : _{r['centre']}_",
        f"*MÉDECINE GÉNÉRALE* : _{r['med_gen']}_ ({r['med_gen_count']} actes)",
        f"*MÉDECINE MANUELLE* : _{r['med_man']}_ ({r['med_man_count']} actes)",
        f"*PHARMACIE* : _{r['pharmacy']}_ ({r['sales_count']} ventes)",
        f"*LABORATOIRE* : _{r['laboratory']}_ ({r['lab_count']} examens)",
        f"*SOINS À DOMICILE* : _{r['home_care']}_ ({r['home_care_count']} prestations)",
        f"*TOTAL PERÇUS* : _{r['total_percus']}_", "",
        f"*DÉPENSES ({r['expenses_count']})* : _{r['total_depenses']}_", "",
        "*SOLDE NET DU MOIS :*",
        f"_{r['solde']}_", "",
        "*Cordialement* 🙌",
    ]
    return '\n'.join(lines)


# ================= ANNUEL =================

def annual_report(year):
    MOIS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
            'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    months = []
    tot_percus = {'USD': 0, 'FC': 0}
    tot_dep = {'USD': 0, 'FC': 0}
    tot_patients = 0

    for m in range(1, 13):
        payments = Payment.objects.filter(date__year=year, date__month=m, status='VALID')
        expenses = Expense.objects.filter(date__year=year, date__month=m)
        sessions = Session.objects.filter(date__year=year, date__month=m)
        per = _sums_by_currency(payments)
        dep = _sums_by_currency(expenses)
        patients = sessions.values('patient').distinct().count()
        tot_percus['USD'] += per['USD']; tot_percus['FC'] += per['FC']
        tot_dep['USD'] += dep['USD']; tot_dep['FC'] += dep['FC']
        tot_patients += patients
        months.append({
            'num': m, 'name': MOIS[m],
            'patients': patients, 'sessions': sessions.count(),
            'percus': _fmt(per), 'depenses': _fmt(dep),
            'percus_usd': float(per['USD']), 'percus_fc': float(per['FC']),
        })

    return {
        'label': str(year),
        'months': months,
        'patients_total': tot_patients,
        'total_percus': _fmt(tot_percus),
        'total_depenses': _fmt(tot_dep),
        'solde': _fmt({'USD': tot_percus['USD'] - tot_dep['USD'],
                       'FC': tot_percus['FC'] - tot_dep['FC']}),
    }


def whatsapp_annual(r):
    lines = [
        f"*RAPPORT ANNUEL — {r['label']}*", "",
        "Bonsoir à tous,", "",
        f"Bilan de l'année : {r['patients_total']} passages patients au total.", "",
        "*TOTAL PERÇUS* : _" + r['total_percus'] + "_",
        "*TOTAL DÉPENSES* : _" + r['total_depenses'] + "_", "",
        "*SOLDE NET DE L'ANNÉE :*",
        f"_{r['solde']}_", "",
        "*Cordialement* 🙌",
    ]
    return '\n'.join(lines)

# ================= ENTREPRISES (ex : LTJ) =================
# Les impayés des patients d'une entreprise « facturée à l'entreprise » ne sont
# PAS des dettes patient : ce sont des CRÉANCES sur l'entreprise, récapitulées
# ici mensuellement (format de l'annexe LTJ).

PRIX_SEANCE_DEFAUT = Decimal('20')   # tarif général d'une séance kiné


def _prix_seance(patient):
    """Prix d'une séance pour ce patient : montant dû (centre) ÷ prescrites,
    sinon tarif général (20 $)."""
    fin = _factures_centre([patient.id])[patient.id]
    if patient.sessions_prescribed > 0 and fin['due'] > 0:
        prix = (fin['due'] / patient.sessions_prescribed).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)
        if prix > 0:
            return prix
    return PRIX_SEANCE_DEFAUT


def company_report(company, year, month):
    """Rapport mensuel des patients d'une entreprise (créances entreprise)."""
    import calendar as _cal
    from apps.finance.models import Invoice, Payment

    MOIS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
            'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    last_day = _cal.monthrange(year, month)[1]

    rows = []
    tot = {'pharmacie': Decimal('0'), 'prescrit': 0, 'effectue': 0,
           'restant': 0, 'cout': Decimal('0')}

    for p in company.patients.all():
        sessions_m = p.sessions.filter(date__year=year, date__month=month,
                                       status='DONE').order_by('date')
        invoices = [i for i in p.invoices
                    .filter(date__year=year, date__month=month)
                    .exclude(status=Invoice.Status.CANCELLED)
                    .prefetch_related('lab_records', 'home_care_services',
                                      'medicine_records')]
        if not sessions_m.exists() and not invoices:
            continue  # aucune activité ce mois → hors rapport

        # « Pharmacie & Autres » = facturé hors séances (pharmacie, labo,
        # médecine, domicile) — la créance naît à la FACTURATION (pas au paiement)
        pharmacie = Decimal('0')
        for inv in invoices:
            if (inv.label.startswith('Pharmacie') or inv.lab_records.exists()
                    or inv.home_care_services.exists() or inv.medicine_records.exists()):
                pharmacie += inv.amount_usd

        effectue = sessions_m.count()
        prescrit = p.sessions_prescribed
        restant = max(prescrit - effectue, 0)
        prix = _prix_seance(p)
        cout = (prix * effectue).quantize(Decimal('0.01'))

        # Colonne Date : plage des séances du mois (« 01-30/07/2026 »)
        if sessions_m.exists():
            d1, d2 = sessions_m.first().date, sessions_m.last().date
            date_txt = (f"{d1:%d/%m/%Y}" if d1 == d2
                        else f"{d1:%d}-{d2:%d/%m/%Y}")
        elif invoices:
            date_txt = f"{min(i.date for i in invoices):%d/%m/%Y}"
        else:
            date_txt = '—'

        obs = []
        obs.append("Séances en cours" if restant > 0 else "Séances terminées")
        if pharmacie > 0:
            obs.append("Pharmacie")

        rows.append({
            'patient': p, 'pharmacie': pharmacie, 'prescrit': prescrit,
            'effectue': effectue, 'restant': restant, 'prix': prix,
            'cout': cout, 'cout_txt': f"{_fmt_nombre(prix)}x{effectue}={_fmt_nombre(cout)}",
            'date_txt': date_txt, 'observation': ' + '.join(obs),
        })
        tot['pharmacie'] += pharmacie
        tot['prescrit'] += prescrit
        tot['effectue'] += effectue
        tot['restant'] += restant
        tot['cout'] += cout

    return {
        'company': company,
        'label': f"{MOIS[month]} {year}",
        'mois_nom': MOIS[month].upper(),
        'year': year, 'month': month,
        'rows': rows,
        'tot': tot,
        'total_general': tot['pharmacie'] + tot['cout'],
        'cloture': f"CLOTURE {last_day:02d}/{month:02d}/{year}",
        'creance_usd': sum(
            i.balance_usd for i in Invoice.objects
            .filter(patient__company=company)
            .exclude(status=Invoice.Status.CANCELLED)
            .prefetch_related('payments')
            if i.balance_usd > 0),
    }
