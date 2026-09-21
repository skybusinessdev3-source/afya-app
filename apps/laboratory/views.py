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
from apps.finance.models import Invoice, Payment
from apps.patients.models import Patient
from apps.settings_app.models import LabExam
from .models import LaboratoryRecord


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


def _norm_prescriber(name):
    """Clé de regroupement insensible à la casse, aux espaces et aux points
    (« Dr.Mutamba Stany » = « Dr. Mutamba Stany »)."""
    return ''.join(ch for ch in (name or '').lower() if ch.isalnum())


@login_required
def lab_page(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    records = LaboratoryRecord.objects.filter(
        date__gte=month_start
    ).select_related('patient', 'exam').order_by('-date', 'patient__last_name')

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
                'exams': [],
                'billed': Decimal('0'), 'prescriber_share': Decimal('0'),
                'lab_share': Decimal('0'), 'center_share': Decimal('0'),
            }
        g['exams'].append({'name': r.exam.name,
                           'amount': r.amount_original,
                           'currency': r.currency_original})
        g['billed'] += r.amount_usd
        g['prescriber_share'] += r.prescriber_amount_usd
        g['lab_share'] += r.lab_team_amount_usd
        g['center_share'] += r.center_amount_usd
    groups = sorted(groups.values(), key=lambda g: (g['date'], g['patient']), reverse=True)

    # --- Résumé par prescripteur : sa part totale du mois en un coup d'œil ---
    presc = {}
    for r in records:
        k = _norm_prescriber(r.prescriber_name)
        p = presc.get(k)
        if p is None:
            p = presc[k] = {'name': r.prescriber_name.strip() or '— Non renseigné —',
                            'share': Decimal('0'), 'exams': 0, 'patients': set()}
        p['share'] += r.prescriber_amount_usd
        p['exams'] += 1
        p['patients'].add(r.patient_id)
    prescriber_summary = sorted(
        ({'name': p['name'], 'share': p['share'], 'exams': p['exams'],
          'patients': len(p['patients'])} for p in presc.values()),
        key=lambda p: p['share'], reverse=True)

    context = {
        'page_title': 'Laboratoire',
        'month_label': today.strftime('%B %Y'),
        'today': today,
        'can_backdate': can_backdate(request.user),
        'exams': LabExam.objects.filter(is_active=True),
        'groups': groups,
        'prescriber_summary': prescriber_summary,
        'totals': {
            'billed': sum(r.amount_usd for r in records),
            'prescriber': sum(r.prescriber_amount_usd for r in records),
            'lab_team': sum(r.lab_team_amount_usd for r in records),
            'center': sum(r.center_amount_usd for r in records),
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

        # --- Paiement éventuel (devise libre → conversion figée par le modèle) ---
        amount_paid = Decimal(str(data.get('amount_paid', '0') or '0'))
        if amount_paid > 0:
            payment = Payment.objects.create(
                invoice=invoice,
                amount_original=amount_paid,
                currency_original=data.get('paid_currency', currency),
                date=op_date,
                received_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        # --- Un enregistrement par examen (splits figés par le modèle) ---
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