from collections import defaultdict
from datetime import date as date_cls

from django.db.models import Sum

from apps.appointments.models import Appointment
from apps.centre.models import Session
from apps.finance.models import Expense, Payment
from apps.laboratory.models import LaboratoryRecord
from apps.home_care.models import HomeCareService
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
    return 'centre'


def _ventilation(payments):
    vent = defaultdict(lambda: {'USD': 0, 'FC': 0})
    for p in payments.select_related('invoice'):
        vent[_categorize(p)][p.currency_original] += p.amount_original
    return vent


# ================= JOURNALIER =================

def daily_report(d):
    sessions = Session.objects.filter(date=d).select_related('patient', 'service')
    payments = Payment.objects.filter(date=d, status=Payment.Status.VALID)
    expenses = Expense.objects.filter(date=d)

    vent = _ventilation(payments)
    patients_lines = []
    for i, s in enumerate(sessions, 1):
        pays = [p for p in payments if p.invoice and p.invoice.patient_id == s.patient_id]
        amounts = {'USD': sum(p.amount_original for p in pays if p.currency_original == 'USD'),
                   'FC': sum(p.amount_original for p in pays if p.currency_original == 'FC')}
        money = f" : {_fmt(amounts)}" if (amounts['USD'] or amounts['FC']) else ""
        seances = f"_{s.patient.sessions_done}/{s.patient.sessions_prescribed}_"
        patients_lines.append(f"{i}. {s.patient.full_name} ({seances}{money})")

    exp_total = _sums_by_currency(expenses)
    total = _sums_by_currency(payments)

    return {
        'label': d.strftime('%d/%m/%Y'),
        'patients_count': sessions.values('patient').distinct().count(),
        'sessions_count': sessions.count(),
        'patients_lines': patients_lines,
        'pharmacy': _fmt(vent['pharmacie']),
        'laboratory': _fmt(vent['laboratoire']),
        'home_care': _fmt(vent['domicile']),
        'centre': _fmt(vent['centre']),
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
        'total_percus': _fmt(total),
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