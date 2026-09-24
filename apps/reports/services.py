from collections import defaultdict
from datetime import date as date_cls
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from apps.appointments.models import Appointment
from apps.centre.models import Session
from apps.finance.models import Expense, Payment, ratio_paye
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
    """Decimal → texte lisible : 20 (jamais '2E+1'), 12.5 (jamais '12.50').
    Arrondi à 2 décimales : jamais de '176.6000000000000000000003'."""
    d = Decimal(d).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    txt = format(d, 'f')
    if '.' in txt:
        txt = txt.rstrip('0').rstrip('.')
    return txt


# ================= JOURNALIER =================

def daily_report(d):
    sessions = Session.objects.filter(date=d).select_related('patient', 'patient__company', 'service')
    payments = (Payment.objects.filter(date=d, status=Payment.Status.VALID)
                .select_related('invoice', 'invoice__patient'))
    expenses = Expense.objects.filter(date=d)

    vent = _ventilation(payments)
    # Avances : factures 'centre' de tous les patients présents ce jour
    pids = {s.patient_id for s in sessions}
    fin = _factures_centre(pids)

    # Produits achetés en pharmacie ce jour, regroupés par patient
    ventes_jour = list(PharmacySale.objects.filter(date=d).select_related('product', 'patient'))
    produits = {}
    for v in ventes_jour:
        if v.patient_id and v.product_id:
            produits.setdefault(v.patient_id, []).append(v)

    def _produits_label(patient_id):
        # '3 Navrox + 2 Orthoglic + Baume' - quantité affichée seulement si > 1
        achats = produits.get(patient_id)
        if not achats:
            return ""
        return " + ".join(
            f"{v.quantity} {v.product.name}" if v.quantity > 1 else v.product.name
            for v in achats)

    def _seances_label(session):
        patient = session.patient
        # Patient d'une ENTREPRISE (LTJ, GGA…) — tout sauf « Privée » :
        # c'est l'entreprise qui paie → on affiche son NOM, pas un compteur.
        if (patient.company_id and patient.company
                and patient.company.name.strip().lower() not in ('privée', 'privee')):
            return f"_{patient.company.name}_"
        # Pas une séance de kiné (évaluation, labo, consultation…) :
        # on affiche le MOTIF, jamais un compteur de séances « 1/0 ».
        if session.motif != Session.Motif.KINE:
            # « Autre » → afficher la PRÉCISION saisie, pas le mot « Autre »
            if session.motif == Session.Motif.OTHER and session.motif_other.strip():
                return f"_{session.motif_other.strip()}_"
            return f"_{session.get_motif_display()}_"
        payees = _seances_payees(fin[patient.id]['due'], fin[patient.id]['paid'],
                                 patient.sessions_prescribed)
        total = _fmt_seances(payees)
        if total is None:                       # pas de tarif calculable → prescrites
            total = patient.sessions_prescribed
        if not total:                           # aucune prescription → texte, pas « 1/0 »
            return f"_{session.get_motif_display()}_"
        return f"_{patient.sessions_done}/{total}_"

    # Une SEULE ligne par patient, même s'il a plusieurs passages ce jour
    # (ex. solde de séances + évaluation) : les libellés se combinent,
    # le montant total du jour n'est affiché qu'une fois.
    patients_lines = []
    par_patient = {}
    for s in sessions:
        info = par_patient.setdefault(s.patient_id,
                                      {'patient': s.patient, 'labels': []})
        label = _seances_label(s)
        if label not in info['labels']:
            info['labels'].append(label)
    for i, (pid, info) in enumerate(par_patient.items(), 1):
        pays = [p for p in payments if p.invoice and p.invoice.patient_id == pid]
        amounts = {'USD': sum(p.amount_original for p in pays if p.currency_original == 'USD'),
                   'FC': sum(p.amount_original for p in pays if p.currency_original == 'FC')}
        money = f" : {_fmt(amounts)}" if (amounts['USD'] or amounts['FC']) else ""
        prods = _produits_label(pid)
        detail = f" ; {prods}" if prods else ""
        seances = ' + '.join(info['labels'])
        patients_lines.append(f"{i}. {info['patient'].full_name} ({seances}{money}{detail})")

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
        prods = _produits_label(pid)
        detail = f" : {prods}" if prods else ""
        i += 1
        patients_lines.append(f"{i}. {info['patient'].full_name} "
                              f"({'/'.join(sorted(info['tags']))}{money}{detail})")

    # --- Paiements de DETTES : facture d'un jour PRÉCÉDENT encaissée ce jour ---
    # Le patient n'a aucun acte aujourd'hui → sans ça il n'apparaîtrait pas au rapport.
    CAT_DETTE = {'laboratoire': 'du labo', 'pharmacie': 'de la pharmacie',
                 'centre': 'du centre', 'domicile': 'des soins à domicile',
                 'medecine_generale': 'de médecine générale',
                 'medecine_manuelle': 'de médecine manuelle'}
    dettes = {}
    for p in payments:
        inv = p.invoice
        if inv is not None and inv.patient_id and inv.date < d:
            dettes.setdefault(inv.patient_id, []).append(p)
    nb_dettes = 0
    for pid, pays in dettes.items():
        if pid in seen or pid in extra:
            continue  # déjà dans la liste : ses paiements du jour y sont affichés
        patient = pays[0].invoice.patient
        amounts = {'USD': sum((p.amount_original for p in pays
                               if p.currency_original == 'USD'), Decimal('0')),
                   'FC': sum((p.amount_original for p in pays
                              if p.currency_original == 'FC'), Decimal('0'))}
        money = _fmt(amounts)
        factures = sorted({p.invoice for p in pays}, key=lambda x: (x.date, x.id))
        if len(factures) == 1:
            inv = factures[0]
            cat = _categorize(next(p for p in pays if p.invoice_id == inv.id))
            txt = (f"Paiement de la dette {CAT_DETTE.get(cat, '')} "
                   f"pour la date du {inv.date:%d/%m/%Y}")
        else:
            parts = []
            for inv in factures:
                cat = _categorize(next(p for p in pays if p.invoice_id == inv.id))
                parts.append(f"{CAT_DETTE.get(cat, 'du centre')} du {inv.date:%d/%m/%Y}")
            txt = f"Paiement de dettes ({' ; '.join(parts)})"
        i += 1
        nb_dettes += 1
        patients_lines.append(f"{i}. {patient.full_name} ({money} : {txt})")

    exp_total = _sums_by_currency(expenses)
    total = _sums_by_currency(payments)

    return {
        'label': d.strftime('%d/%m/%Y'),
        'patients_count': len(seen) + len(extra) + nb_dettes,
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
        'extra': f"Pharmacie : {len(ventes_jour)} vente(s) · "
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

MOIS_FR = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet',
           'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


def month_days_report(year, month):
    """Tous les jours du mois, chacun avec le MÊME contenu que le rapport
    journalier (patients, ventilation, dépenses, solde).
    Les jours sans aucune activité sont omis. Les lignes sont nettoyées
    des marqueurs WhatsApp (* et _) pour un affichage HTML lisible."""
    import calendar

    def _clean(lignes):
        return [l.replace('*', '').replace('_', '').strip() for l in lignes]

    jours = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        r = daily_report(date_cls(year, month, day))
        if (r['sessions_count'] or r['patients_count']
                or r['expense_lines'] or r['total_percus'] != '0'):
            r['patients_lines'] = _clean(r['patients_lines'])
            r['expense_lines'] = _clean(r['expense_lines'])
            jours.append(r)

    # Totaux du mois entier : par activité + total général (bas de page)
    payments = Payment.objects.filter(date__year=year, date__month=month,
                                      status=Payment.Status.VALID)
    expenses = Expense.objects.filter(date__year=year, date__month=month)
    vent = _ventilation(payments)
    exp_total = _sums_by_currency(expenses)
    total = _sums_by_currency(payments)
    totaux = {
        'centre': _fmt(vent['centre']),
        'med_gen': _fmt(vent['medecine_generale']),
        'med_man': _fmt(vent['medecine_manuelle']),
        'pharmacie': _fmt(vent['pharmacie']),
        'laboratoire': _fmt(vent['laboratoire']),
        'domicile': _fmt(vent['domicile']),
        'total_percus': _fmt(total),
        'total_depenses': _fmt(exp_total),
        'solde': _fmt({'USD': total['USD'] - exp_total['USD'],
                       'FC': total['FC'] - exp_total['FC']}),
    }
    return {'label': f"{MOIS_FR[month]} {year}", 'jours': jours,
            'totaux': totaux}


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


# ================= PRESCRIPTEURS & ACTIVITÉS =================

NON_RENSEIGNE = '— Non renseigné —'

# Onglets du rapport par activité : (slug, libellé court)
ACTIVITES = [
    ('centre', 'Centre'),
    ('medecine-generale', 'Méd. générale'),
    ('medecine-manuelle', 'Méd. manuelle'),
    ('pharmacie', 'Pharmacie'),
    ('labo', 'Laboratoire'),
    ('domicile', 'Domicile'),
]


TITRES_PRESCRIPTEUR = ('dr', 'docteur', 'docteure', 'doct', 'pr', 'prof', 'professeur')


def _canon_prescriber(name):
    """Uniformise le titre pour l'AFFICHAGE :
    « Docteur Mutamba Stany » / « Dr Mutamba Stany » → « Dr. Mutamba Stany »."""
    txt = ' '.join(str(name or '').split())
    parts = txt.split(None, 1)
    if len(parts) == 2 and parts[0].lower().rstrip('.') in TITRES_PRESCRIPTEUR:
        return f"Dr. {parts[1]}"
    return txt


def _norm_prescriber_name(name):
    """Normalise un nom de prescripteur pour le regroupement :
    casse, espaces, points ET titre ignorés —
    « Docteur Mutamba Stany » = « Dr. Mutamba Stany » = « Mutamba Stany ».
    (« / » → espace : la clé transite dans l'URL.)"""
    if not name:
        return ''
    txt = ' '.join(str(name).replace('/', ' ').replace('.', ' ').split()).lower()
    mots = txt.split()
    if mots and mots[0] in TITRES_PRESCRIPTEUR:
        mots = mots[1:]                      # le titre ne fait pas partie de la clé
    return ' '.join(mots)


def _prescriber_display(record):
    """Nom affiché : prescriber_name libre, sinon FK Staff, sinon placeholder.
    Le titre est uniformisé (« Docteur X » → « Dr. X »)."""
    name = getattr(record, 'prescriber_name', '') or ''
    if name.strip():
        return _canon_prescriber(name)
    prescriber = getattr(record, 'prescriber', None)
    if prescriber is not None:
        return _canon_prescriber(str(prescriber))
    return NON_RENSEIGNE


def _med_family(category):
    """GENERAL_* → 'generale', MANUAL* → 'manuelle'."""
    return 'manuelle' if (category or '').startswith('MANUAL') else 'generale'


def _med_detail(record):
    """Prestation affichée : catégorie + précision éventuelle."""
    label = record.get_category_display()
    if record.prestation_other:
        label += f" — {record.prestation_other}"
    return label


def _date_txt(d):
    return f"{d:%d/%m/%Y}"


def prescribers_summary(d1, d2):
    """Liste des prescripteurs (labo + médecine) ayant des actes entre d1 et d2
    inclus, regroupés par nom normalisé, triés par nom."""
    summary = {}

    def _touch(record, kind):
        name = _prescriber_display(record)
        key = _norm_prescriber_name(name)
        entry = summary.setdefault(key, {
            'key': key, 'name': name,
            'labo_count': 0, 'labo_share': Decimal('0'),
            'med_count': 0, 'med_share': Decimal('0'),
            'paid_share': Decimal('0'), 'unpaid_share': Decimal('0'),
        })
        # Variantes du même prescripteur fusionnées : préfère la forme « Dr. … »
        if name.startswith('Dr. ') and not entry['name'].startswith('Dr. '):
            entry['name'] = name
        entry[f'{kind}_count'] += 1
        # Part sur l'ENCAISSÉ, pas le facturé (arrondie comme au rapport détaillé)
        part = ((record.prescriber_amount_usd or Decimal('0'))
                * ratio_paye(record.invoice)).quantize(Decimal('0.01'),
                                                       rounding=ROUND_HALF_UP)
        entry[f'{kind}_share'] += part
        # Suivi du versement : déjà payée au prescripteur ou encore à verser
        if getattr(record, 'prescriber_paid', False):
            entry['paid_share'] += part
        else:
            entry['unpaid_share'] += part

    for r in (LaboratoryRecord.objects
              .filter(date__gte=d1, date__lte=d2)
              .select_related('prescriber', 'invoice')
              .prefetch_related('invoice__payments')):
        _touch(r, 'labo')
    for r in (MedicineRecord.objects.filter(date__gte=d1, date__lte=d2)
              .select_related('invoice')
              .prefetch_related('invoice__payments')):
        _touch(r, 'med')

    rows = sorted(summary.values(), key=lambda e: e['name'].casefold())
    for e in rows:
        e['total_share'] = e['labo_share'] + e['med_share']
        e['labo_share_txt'] = _fmt_nombre(e['labo_share'])
        e['med_share_txt'] = _fmt_nombre(e['med_share'])
        e['total_share_txt'] = _fmt_nombre(e['total_share'])
        e['paid_share_txt'] = _fmt_nombre(e['paid_share'])
        e['unpaid_share_txt'] = _fmt_nombre(e['unpaid_share'])
    return rows


def prescriber_report(key, d1, d2):
    """Rapport individuel d'un prescripteur : tous ses actes (labo + médecine)
    entre d1 et d2, triés par date."""
    key_norm = _norm_prescriber_name(key)
    rows = []
    display_name = None

    for r in (LaboratoryRecord.objects
              .filter(date__gte=d1, date__lte=d2)
              .select_related('prescriber', 'patient', 'exam', 'invoice')
              .prefetch_related('invoice__payments')):
        name = _prescriber_display(r)
        if _norm_prescriber_name(name) != key_norm:
            continue
        if display_name is None or (name.startswith('Dr. ')
                                    and not display_name.startswith('Dr. ')):
            display_name = name
        rows.append({
            'date': r.date, 'date_txt': _date_txt(r.date),
            'activite': 'Labo',
            'patient': r.patient.full_name,
            'detail': r.exam.name,
            'montant_usd': r.amount_usd,
            'part_usd': (r.prescriber_amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01')),
            'montant_txt': _fmt_nombre(r.amount_usd),
            'part_txt': _fmt_nombre(
                (r.prescriber_amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01'))),
            'prescriber_paid': bool(r.prescriber_paid),
            'part_statut': 'Versée' if r.prescriber_paid else 'En attente',
            'observation': r.observation or '',
        })

    for r in (MedicineRecord.objects
              .filter(date__gte=d1, date__lte=d2)
              .select_related('patient', 'invoice')
              .prefetch_related('invoice__payments')):
        name = _prescriber_display(r)
        if _norm_prescriber_name(name) != key_norm:
            continue
        if display_name is None or (name.startswith('Dr. ')
                                    and not display_name.startswith('Dr. ')):
            display_name = name
        rows.append({
            'date': r.date, 'date_txt': _date_txt(r.date),
            'activite': 'Méd. manuelle' if _med_family(r.category) == 'manuelle' else 'Méd. générale',
            'patient': r.patient.full_name,
            'detail': _med_detail(r),
            'montant_usd': r.amount_usd,
            'part_usd': (r.prescriber_amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01')),
            'montant_txt': _fmt_nombre(r.amount_usd),
            'part_txt': _fmt_nombre(
                (r.prescriber_amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01'))),
            'prescriber_paid': bool(r.prescriber_paid),
            'part_statut': 'Versée' if r.prescriber_paid else 'En attente',
            'observation': r.observation or '',
        })

    rows.sort(key=lambda x: (x['date'], x['activite'], x['patient']))
    total_billed = sum((x['montant_usd'] for x in rows), Decimal('0'))
    total_share = sum((x['part_usd'] for x in rows), Decimal('0'))
    total_paid = sum((x['part_usd'] for x in rows if x['prescriber_paid']), Decimal('0'))
    total_unpaid = total_share - total_paid

    return {
        'name': display_name or key,
        'd1': d1, 'd2': d2,
        'periode_txt': f"du {_date_txt(d1)} au {_date_txt(d2)}",
        'rows': rows,
        'total_billed': total_billed,
        'total_share': total_share,
        'total_billed_txt': _fmt_nombre(total_billed),
        'total_share_txt': _fmt_nombre(total_share),
        'total_paid_txt': _fmt_nombre(total_paid),
        'total_unpaid_txt': _fmt_nombre(total_unpaid),
    }


def _factures_centre_par_jour(patient_ids, d1, d2):
    """(patient_id, date) → liste des factures 'centre' du jour
    (on exclut pharmacie, labo, médecine, domicile et les annulées)."""
    from apps.finance.models import Invoice
    res = defaultdict(list)
    if not patient_ids:
        return res
    invoices = (Invoice.objects
                .filter(patient_id__in=patient_ids, date__gte=d1, date__lte=d2)
                .exclude(status=Invoice.Status.CANCELLED)
                .prefetch_related('lab_records', 'home_care_services',
                                  'medicine_records', 'payments'))
    for inv in invoices:
        if (inv.label.startswith('Pharmacie') or inv.lab_records.exists()
                or inv.home_care_services.exists() or inv.medicine_records.exists()):
            continue
        res[(inv.patient_id, inv.date)].append(inv)
    return res


def _activity_result(slug, titre, d1, d2, columns, rows, totals_map, total_usd, total_qty=None):
    """Assemble le dict prêt pour template et exports.
    totals_map : {index_colonne: texte} pour la ligne TOTAL."""
    total_row = ['TOTAL'] + [''] * (len(columns) - 1)
    for idx, txt in totals_map.items():
        total_row[idx] = txt
    return {
        'slug': slug, 'titre': titre,
        'd1': d1, 'd2': d2,
        'periode_txt': f"du {_date_txt(d1)} au {_date_txt(d2)}",
        'columns': columns,
        'rows': rows,
        'total_row': total_row,
        'total_usd': total_usd,
        'total_usd_txt': _fmt_nombre(total_usd),
        'total_qty': total_qty,
    }


def activity_report(slug, d1, d2):
    """Rapport détaillé d'une activité entre d1 et d2 (inclus).

    Chaque ligne affiche le FACTURÉ et le PAYÉ (réellement encaissé) —
    le total de référence est le PAYÉ, jamais le montant dû.
    Retourne None si le slug est inconnu."""
    if slug == 'centre':
        sessions = list(Session.objects
                        .filter(date__gte=d1, date__lte=d2)
                        .select_related('patient', 'service')
                        .order_by('date', 'patient__last_name'))
        factures = _factures_centre_par_jour({s.patient_id for s in sessions}, d1, d2)
        columns = ['Date', 'Patient', 'Motif / Service', 'Facturé ($)', 'Payé ($)']
        rows = []
        tot_fact, tot_paye = Decimal('0'), Decimal('0')
        for s in sessions:
            invs = factures.get((s.patient_id, s.date), [])
            if invs:
                fact = sum((i.amount_usd for i in invs), Decimal('0'))
                paye = sum((i.amount_paid_usd for i in invs), Decimal('0'))
            elif s.service_id and s.service.price_usd:
                fact, paye = s.service.price_usd, Decimal('0')
            else:
                fact, paye = Decimal('0'), Decimal('0')
            detail = s.get_motif_display()
            if s.service_id:
                detail += f" ({s.service.name})"
            if s.motif == Session.Motif.OTHER and s.motif_other:
                detail += f" — {s.motif_other}"
            tot_fact += fact
            tot_paye += paye
            rows.append([_date_txt(s.date), s.patient.full_name, detail,
                         _fmt_nombre(fact) if fact else '—',
                         _fmt_nombre(paye) if paye else '—'])
        return _activity_result(slug, 'RAPPORT CENTRE — SÉANCES & CONSULTATIONS',
                                d1, d2, columns, rows,
                                {3: _fmt_nombre(tot_fact), 4: _fmt_nombre(tot_paye)},
                                tot_paye)

    if slug == 'pharmacie':
        from apps.finance.models import Invoice
        ventes = list(PharmacySale.objects
                      .filter(date__gte=d1, date__lte=d2)
                      .select_related('product', 'patient')
                      .order_by('date', 'id'))
        # Factures pharmacie par (patient, jour) → payé réparti au prorata des ventes
        par_jour = defaultdict(list)
        for inv in (Invoice.objects
                    .filter(date__gte=d1, date__lte=d2, label__startswith='Pharmacie')
                    .exclude(status=Invoice.Status.CANCELLED)
                    .prefetch_related('payments')):
            par_jour[(inv.patient_id, inv.date)].append(inv)
        ventes_jour = defaultdict(lambda: Decimal('0'))
        for v in ventes:
            ventes_jour[(v.patient_id, v.date)] += v.total_usd
        columns = ['Date', 'Patient', 'Produit', 'Quantité',
                   'Prix unit. ($)', 'Facturé ($)', 'Payé ($)']
        rows = []
        tot_fact, tot_paye, total_qty = Decimal('0'), Decimal('0'), 0
        for v in ventes:
            invs_j = par_jour.get((v.patient_id, v.date), [])
            paye_j = sum((i.amount_paid_usd for i in invs_j), Decimal('0'))
            total_j = ventes_jour[(v.patient_id, v.date)]
            paye = (paye_j * (v.total_usd / total_j)).quantize(Decimal('0.01')) \
                if total_j > 0 else Decimal('0')
            tot_fact += v.total_usd
            tot_paye += paye
            total_qty += v.quantity
            rows.append([_date_txt(v.date),
                         v.patient.full_name if v.patient else 'Client comptant',
                         v.product.name, str(v.quantity),
                         _fmt_nombre(v.unit_price_usd), _fmt_nombre(v.total_usd),
                         _fmt_nombre(paye)])
        return _activity_result(slug, 'RAPPORT PHARMACIE — VENTES',
                                d1, d2, columns, rows,
                                {3: str(total_qty), 5: _fmt_nombre(tot_fact),
                                 6: _fmt_nombre(tot_paye)},
                                tot_paye, total_qty=total_qty)

    if slug == 'labo':
        # Groupé par patient : le détail examen par examen reste visible
        # dans la page Laboratoire ; ici on veut une synthèse lisible.
        records = (LaboratoryRecord.objects
                   .filter(date__gte=d1, date__lte=d2)
                   .select_related('patient', 'invoice')
                   .prefetch_related('invoice__payments'))
        columns = ['Patient', 'Examens (nb)', 'Facturé ($)', 'Payé ($)']
        par_patient = {}
        for r in records:
            paye = (r.amount_usd * ratio_paye(r.invoice)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP)
            e = par_patient.setdefault(r.patient_id, {
                'nom': r.patient.full_name if r.patient else '—',
                'nb': 0, 'fact': Decimal('0'), 'paye': Decimal('0')})
            e['nb'] += 1
            e['fact'] += r.amount_usd
            e['paye'] += paye
        rows = []
        tot_fact, tot_paye, tot_nb = Decimal('0'), Decimal('0'), 0
        for e in sorted(par_patient.values(), key=lambda x: x['nom'].casefold()):
            tot_fact += e['fact']
            tot_paye += e['paye']
            tot_nb += e['nb']
            rows.append([e['nom'], str(e['nb']),
                         _fmt_nombre(e['fact']), _fmt_nombre(e['paye'])])
        return _activity_result(slug, 'RAPPORT LABORATOIRE — PAR PATIENT',
                                d1, d2, columns, rows,
                                {1: str(tot_nb), 2: _fmt_nombre(tot_fact),
                                 3: _fmt_nombre(tot_paye)},
                                tot_paye, total_qty=tot_nb)

    if slug in ('medecine-generale', 'medecine-manuelle'):
        famille = 'manuelle' if slug == 'medecine-manuelle' else 'generale'
        records = [r for r in (MedicineRecord.objects
                               .filter(date__gte=d1, date__lte=d2)
                               .select_related('patient', 'invoice')
                               .prefetch_related('invoice__payments')
                               .order_by('date', 'id'))
                   if _med_family(r.category) == famille]
        columns = ['Date', 'Patient', 'Prestation', 'Prescripteur',
                   'Facturé ($)', 'Payé ($)']
        rows = []
        tot_fact, tot_paye = Decimal('0'), Decimal('0')
        for r in records:
            paye = (r.amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01'))
            tot_fact += r.amount_usd
            tot_paye += paye
            rows.append([_date_txt(r.date), r.patient.full_name, _med_detail(r),
                         _prescriber_display(r), _fmt_nombre(r.amount_usd),
                         _fmt_nombre(paye)])
        titre = ('RAPPORT MÉDECINE MANUELLE' if famille == 'manuelle'
                 else 'RAPPORT MÉDECINE GÉNÉRALE')
        return _activity_result(slug, titre, d1, d2, columns, rows,
                                {4: _fmt_nombre(tot_fact), 5: _fmt_nombre(tot_paye)},
                                tot_paye)

    if slug == 'domicile':
        services_qs = (HomeCareService.objects
                       .filter(date__gte=d1, date__lte=d2)
                       .select_related('patient', 'doctor', 'invoice')
                       .prefetch_related('invoice__payments')
                       .order_by('date', 'id'))
        columns = ['Date', 'Patient', 'Prestation', 'Médecin', 'Facturé ($)', 'Payé ($)']
        rows = []
        tot_fact, tot_paye = Decimal('0'), Decimal('0')
        for s in services_qs:
            fact = (s.invoice.amount_usd
                    if s.invoice_id and s.invoice.status != 'CANCELLED' else None)
            paye = s.invoice.amount_paid_usd if fact else None
            if fact:
                tot_fact += fact
            if paye:
                tot_paye += paye
            prestation = (f"Soins à domicile — {s.sessions_done}/{s.sessions_prescribed} "
                          f"séance(s)")
            rows.append([_date_txt(s.date), s.patient.full_name, prestation,
                         str(s.doctor) if s.doctor_id else '—',
                         _fmt_nombre(fact) if fact else '—',
                         _fmt_nombre(paye) if paye else '—'])
        return _activity_result(slug, 'RAPPORT SOINS À DOMICILE',
                                d1, d2, columns, rows,
                                {4: _fmt_nombre(tot_fact), 5: _fmt_nombre(tot_paye)},
                                tot_paye)

    return None
