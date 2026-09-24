import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.core.utils import can_backdate, parse_operation_date
from apps.finance.models import Invoice, Payment, ratio_paye
from apps.finance.views import _creance_info
from apps.patients.models import Patient
from apps.settings_app.models import LabExam
from .models import LaboratoryRecord


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


def _norm_prescriber(name):
    """Clé de regroupement : casse, espaces, points ET titre ignorés
    (« Docteur Mutamba Stany » = « Dr. Mutamba Stany » = « Mutamba Stany »).
    Délègue à la normalisation canonique des rapports (source unique)."""
    from apps.reports.services import _norm_prescriber_name
    return ''.join(ch for ch in _norm_prescriber_name(name) if ch.isalnum())


@login_required
def lab_page(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    records = (LaboratoryRecord.objects.filter(date__gte=month_start)
               .select_related('patient', 'exam', 'invoice')
               .prefetch_related('invoice__payments')
               .order_by('-date', 'patient__last_name'))

    # --- Regroupement : 1 ligne par date + patient + prescripteur ---
    # (le détail des examens s'affiche au clic dans le template)
    groups = {}
    for r in records:
        key = (r.date, r.patient_id, _norm_prescriber(r.prescriber_name))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                'date': r.date,
                'patient': r.patient.full_name,
                'prescriber': r.prescriber_name.strip() or '— Non renseigné —',
                'exams': [], 'ids': [],
                'billed': Decimal('0'), 'prescriber_share': Decimal('0'),
                'lab_share': Decimal('0'), 'center_share': Decimal('0'),
                'billed_par_invoice': {},
                'prescriber_paid_all': True,
            }
        g['ids'].append(r.id)
        g['prescriber_paid_all'] = g['prescriber_paid_all'] and r.prescriber_paid
        g['exams'].append({'name': r.exam.name,
                           'amount': r.amount_original,
                           'currency': r.currency_original})
        g['billed'] += r.amount_usd
        if r.invoice_id:
            g['billed_par_invoice'][r.invoice_id] = (
                g['billed_par_invoice'].get(r.invoice_id, Decimal('0')) + r.amount_usd)
        rt = ratio_paye(r.invoice)          # parts sur l'ENCAISSÉ, pas le facturé
        g['prescriber_share'] += (r.prescriber_amount_usd * rt).quantize(Decimal('0.01'))
        g['lab_share'] += (r.lab_team_amount_usd * rt).quantize(Decimal('0.01'))
        g['center_share'] += (r.center_amount_usd * rt).quantize(Decimal('0.01'))
    groups = sorted(groups.values(), key=lambda g: (g['date'], g['patient']), reverse=True)

    # --- Payé / Reste par groupe via les factures liées ---
    # (prorata si une facture est partagée entre 2 groupes, ex. 2 prescripteurs)
    inv_ids = {iid for g in groups for iid in g['billed_par_invoice']}
    inv_map = {inv.id: inv for inv in Invoice.objects.filter(id__in=inv_ids)}
    for g in groups:
        paid = Decimal('0')
        for iid, part in g['billed_par_invoice'].items():
            inv = inv_map.get(iid)
            if inv is not None and inv.amount_usd and inv.amount_usd > 0:
                paid += inv.amount_paid_usd * (part / inv.amount_usd)
        g['paid'] = paid.quantize(Decimal('0.01'))
        g['debt'] = max(g['billed'] - g['paid'], Decimal('0')).quantize(Decimal('0.01'))

    # --- Résumé par prescripteur : sa part totale du mois en un coup d'œil ---
    presc = {}
    for r in records:
        k = _norm_prescriber(r.prescriber_name)
        p = presc.get(k)
        if p is None:
            p = presc[k] = {'name': r.prescriber_name.strip() or '— Non renseigné —',
                            'share': Decimal('0'), 'exams': 0, 'patients': set()}
        p['share'] += (r.prescriber_amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01'))
        p['exams'] += 1
        p['patients'].add(r.patient_id)
    prescriber_summary = sorted(
        ({'name': p['name'], 'share': p['share'], 'exams': p['exams'],
          'patients': len(p['patients'])} for p in presc.values()),
        key=lambda p: p['share'], reverse=True)

    # --- Parts prescripteur pas encore marquées « versées » (mois affiché) ---
    # Bandeau de rappel : ces montants restent à régler aux prescripteurs.
    parts_attente = [r for r in records
                     if r.prescriber_amount_usd > 0 and not r.prescriber_paid
                     and (r.prescriber_name or '').strip()]
    parts_attente_total = sum(
        ((r.prescriber_amount_usd * ratio_paye(r.invoice)).quantize(Decimal('0.01'))
         for r in parts_attente), Decimal('0'))

    context = {
        'page_title': 'Laboratoire',
        'month_label': today.strftime('%B %Y'),
        'today': today,
        'can_backdate': can_backdate(request.user),
        'exams': LabExam.objects.filter(is_active=True),
        'groups': groups,
        'prescriber_summary': prescriber_summary,
        'parts_attente_count': len(parts_attente),
        'parts_attente_total': parts_attente_total,
        'totals': {
            'billed': sum(r.amount_usd for r in records),
            'paid': sum((g['paid'] for g in groups), Decimal('0')),
            'debt': sum((g['debt'] for g in groups), Decimal('0')),
            # Totaux = somme des parts déjà arrondies des groupes : l'affichage
            # est cohérent au centime (jamais de '176,6000000000000000000003').
            'prescriber': sum((g['prescriber_share'] for g in groups), Decimal('0')),
            'lab_team': sum((g['lab_share'] for g in groups), Decimal('0')),
            'center': sum((g['center_share'] for g in groups), Decimal('0')),
        },
    }
    return render(request, 'laboratory/index.html', context)


@login_required
@require_POST
@transaction.atomic
def lab_record_create(request):
    """
    Enregistre UN OU PLUSIEURS examens pour un patient :
    - total facturé recalculé CÔTÉ SERVEUR depuis les prix du catalogue (§3.1)
    - une facture unique + un paiement éventuel (devise libre, conversion figée)
    - un enregistrement par examen avec répartition 20/60/40 figée (§12.1)
    """
    try:
        data = json.loads(request.body)
        patient = Patient.objects.get(pk=data['patient_id'], is_active=True)

        exam_ids = data.get('exam_ids', [])
        exams = list(LabExam.objects.filter(id__in=exam_ids, is_active=True))
        if not exams:
            return JsonResponse({'success': False, 'message': "Sélectionnez au moins un examen."}, status=400)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        currency = data.get('currency', 'USD')
        # Total recalculé serveur (jamais celui envoyé par le navigateur)
        total_usd = sum(e.price_usd for e in exams)
        total_fc = sum(e.price_fc for e in exams)
        due = total_fc if currency == 'FC' else total_usd
        if due <= 0:
            return JsonResponse({'success': False, 'message': "Total à 0 — vérifiez les prix du catalogue."}, status=400)

        # --- Facture unique ---
        invoice = Invoice.objects.create(
            patient=patient,
            label="Laboratoire — " + ", ".join(e.name for e in exams)[:200],
            amount_original=due,
            currency_original=currency,
            date=op_date,
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=invoice, ip_address=get_client_ip(request))

        # --- Paiements éventuels — 1 ou 2 devises (paiement mixte $ + FC) ---
        cur1 = data.get('paid_currency', currency)
        paiements = [
            (Decimal(str(data.get('amount_paid', '0') or '0')), cur1),
            (Decimal(str(data.get('amount_paid2', '0') or '0')),
             data.get('paid_currency2') or ('FC' if cur1 == 'USD' else 'USD')),
        ]
        paiements = [(a, c) for a, c in paiements if a > 0]
        for amount_paid, cur in paiements:
            payment = Payment.objects.create(
                invoice=invoice,
                amount_original=amount_paid,
                currency_original=cur,
                date=op_date,
                received_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        # --- Un enregistrement par examen (splits figés par le modèle) ---
        # Le prescripteur peut avoir déjà reçu sa part le jour même (case à cocher)
        part_deja_versee = bool(data.get('prescriber_paid'))
        for exam in exams:
            record = LaboratoryRecord.objects.create(
                patient=patient,
                exam=exam,
                prescriber_name=data.get('prescriber_name', '').strip(),
                invoice=invoice,
                date=op_date,
                amount_original=exam.price_fc if currency == 'FC' else exam.price_usd,
                currency_original=currency,
                status=LaboratoryRecord.Status.DONE,
                prescriber_paid=part_deja_versee,
                prescriber_paid_on=op_date if part_deja_versee else None,
                observation=data.get('observation', ''),
                created_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='laboratory', obj=record, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"{len(exams)} examen(s) enregistré(s) pour {patient.full_name}.",
            'total_usd': float(total_usd),
            'total_fc': float(total_fc),
            'creance': _creance_info(invoice),
        })

    except (Patient.DoesNotExist, LabExam.DoesNotExist):
        return JsonResponse({'success': False, 'message': "Patient ou examen introuvable."}, status=404)
    except (InvalidOperation, ValueError, KeyError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)


@login_required
@require_POST
@transaction.atomic
def lab_exam_create(request):
    """Crée un examen de laboratoire (catalogue)."""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        price_usd = Decimal(str(data.get('price_usd', '0')))
        price_fc = Decimal(str(data.get('price_fc', '0')))

        if not name or price_usd <= 0 or price_fc <= 0:
            return JsonResponse({'success': False, 'message': "Nom et prix ($ et FC) obligatoires."}, status=400)
        if LabExam.objects.filter(name__iexact=name).exists():
            return JsonResponse({'success': False, 'message': "Cet examen existe déjà."}, status=400)

        exam = LabExam.objects.create(
            name=name,
            price_usd=price_usd,
            price_fc=price_fc,
            observation=data.get('observation', ''),
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='settings_app', obj=exam, ip_address=get_client_ip(request))

        return JsonResponse({'success': True, 'message': f"Examen « {exam.name} » créé."})

    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)

@login_required
@require_POST
@transaction.atomic
def lab_prescriber_paid(request):
    """Marque la part prescripteur d'un ou plusieurs examens comme versée (ou non).
    Réservé aux responsables — c'est un mouvement de caisse."""
    if not can_backdate(request.user):
        return JsonResponse({'success': False,
                             'message': "Réservé aux responsables."}, status=403)
    try:
        data = json.loads(request.body)
        ids = [int(i) for i in data.get('ids', [])]
        paid = bool(data.get('paid', True))
        if not ids:
            return JsonResponse({'success': False,
                                 'message': "Aucun examen visé."}, status=400)
        records = list(LaboratoryRecord.objects.filter(id__in=ids))
        if not records:
            return JsonResponse({'success': False,
                                 'message': "Examens introuvables."}, status=404)
        today = timezone.localdate()
        for r in records:
            r.prescriber_paid = paid
            r.prescriber_paid_on = today if paid else None
            r.save(update_fields=['prescriber_paid', 'prescriber_paid_on'])
            log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                      module='laboratory', obj=r, ip_address=get_client_ip(request))
        return JsonResponse({
            'success': True,
            'message': (f"Part prescripteur marquée « versée » pour {len(records)} examen(s)."
                        if paid else
                        f"Part prescripteur remise « en attente » pour {len(records)} examen(s)."),
        })
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)
