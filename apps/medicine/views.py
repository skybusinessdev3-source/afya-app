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
from apps.settings_app.models import MedicineSplitConfig, PrescriberConfig, Staff
from .models import MedicineRecord


def get_client_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0] if x else request.META.get('REMOTE_ADDR')


def _page(request, categories, title):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    records = list(MedicineRecord.objects.filter(
        category__in=categories, date__gte=month_start
    ).select_related('patient', 'invoice').prefetch_related('invoice__payments').order_by('-date'))

    # Parts sur l'ENCAISSÉ (prorata du paiement de la facture), pas le facturé
    for r in records:
        rt = ratio_paye(r.invoice)
        r.part_presc_paye = (r.prescriber_amount_usd * rt).quantize(Decimal('0.01'))
        r.part_centre_paye = (r.center_amount_usd * rt).quantize(Decimal('0.01'))

    pcts = {}
    for cat in categories:
        cfg = MedicineSplitConfig.objects.filter(category=cat, is_active=True).first()
        pcts[cat] = float(cfg.prescriber_pct) if cfg else 0

    # Médecins du centre (docteurs de préférence, sinon tout le personnel actif)
    medecins = Staff.objects.filter(is_active=True, title=Staff.Titles.DOCTOR)
    if not medecins.exists():
        medecins = Staff.objects.filter(is_active=True)

    # Configs individuelles par médecin — pour l'aperçu JS
    configs_medecins = {}
    for cfg in PrescriberConfig.objects.filter(is_active=True):
        configs_medecins.setdefault(cfg.staff_id, {})[cfg.category] = {
            'tariff': float(cfg.tariff_usd), 'pct': float(cfg.prescriber_pct),
        }

    # Parts prescripteur pas encore marquées « versées » (mois affiché)
    parts_attente = [r for r in records
                     if r.prescriber_amount_usd > 0 and not r.prescriber_paid]

    return render(request, 'medicine/index.html', {
        'page_title': title,
        'month_label': today.strftime('%B %Y'),
        'today': today,
        'can_backdate': can_backdate(request.user),
        'categories': MedicineSplitConfig.Categories,
        'allowed': [c for c in MedicineSplitConfig.Categories.values if c in categories],
        'pcts': pcts,
        'medecins': medecins,
        'configs_medecins': json.dumps(configs_medecins),
        'records': records,
        'parts_attente_count': len(parts_attente),
        'parts_attente_total': sum((r.part_presc_paye for r in parts_attente), Decimal('0')),
        'totals': {
            'billed': sum(r.amount_usd for r in records),
            'prescriber': sum((r.part_presc_paye for r in records), Decimal('0')),
            'center': sum((r.part_centre_paye for r in records), Decimal('0')),
        },
    })


@login_required
def general_page(request):
    return _page(request, ['GENERAL_CONSULTATION', 'GENERAL_OTHER'], 'Médecine générale')


@login_required
def manual_page(request):
    return _page(request, ['MANUAL', 'MANUAL_OTHER'], 'Médecine manuelle')


@login_required
@require_POST
@transaction.atomic
def record_create(request):
    """Prestation médecine + facture + paiement éventuel (splits figés par le modèle)."""
    try:
        data = json.loads(request.body)
        patient = Patient.objects.get(pk=data['patient_id'], is_active=True)
        amount = Decimal(str(data.get('amount', '0')))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        currency = data.get('currency', 'USD')

        # Médecin du centre (Staff) — sinon nom libre (prescripteur externe)
        prescriber = None
        prescriber_id = data.get('prescriber_id') or None
        if prescriber_id:
            try:
                prescriber = Staff.objects.get(pk=int(prescriber_id), is_active=True)
            except (Staff.DoesNotExist, TypeError, ValueError):
                return JsonResponse({'success': False, 'message': "Médecin introuvable."}, status=404)
        prescriber_name = str(prescriber) if prescriber else data.get('prescriber_name', '').strip()

        # Le prescripteur peut avoir déjà reçu sa part le jour même (case à cocher)
        part_deja_versee = bool(data.get('prescriber_paid'))
        record = MedicineRecord.objects.create(
            patient=patient,
            category=data['category'],
            date=op_date,
            prescriber=prescriber,
            prescriber_name=prescriber_name,
            prestation_other=data.get('prestation_other', '').strip(),
            amount_original=amount,
            currency_original=currency,
            status=MedicineRecord.Status.DONE,
            prescriber_paid=part_deja_versee,
            prescriber_paid_on=op_date if part_deja_versee else None,
            observation=data.get('observation', ''),
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='medicine', obj=record, ip_address=get_client_ip(request))

        invoice = Invoice.objects.create(
            patient=patient,
            label=f"{record.get_category_display()}"
                  + (f" ({record.prestation_other})" if record.prestation_other else "")
                  + f" — {record.date:%d/%m/%Y}",
            amount_original=amount,
            currency_original=currency,
            date=op_date,
            created_by=request.user,
        )
        record.invoice = invoice
        record.save(update_fields=['invoice'])
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

        return JsonResponse({
            'success': True,
            'message': f"{record.get_category_display()} enregistrée pour {patient.full_name}.",
            'splits': {'prescriber': float(
                           record.prescriber_amount_usd * ratio_paye(record.invoice)),
                       'center': float(
                           record.center_amount_usd * ratio_paye(record.invoice))},
            'creance': _creance_info(invoice),
        })
    except (Patient.DoesNotExist, KeyError):
        return JsonResponse({'success': False, 'message': "Patient introuvable."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)

@login_required
@require_POST
@transaction.atomic
def med_prescriber_paid(request):
    """Marque la part prescripteur d'une ou plusieurs prestations comme versée
    (ou non). Réservé aux responsables — c'est un mouvement de caisse."""
    if not can_backdate(request.user):
        return JsonResponse({'success': False,
                             'message': "Réservé aux responsables."}, status=403)
    try:
        data = json.loads(request.body)
        ids = [int(i) for i in data.get('ids', [])]
        paid = bool(data.get('paid', True))
        if not ids:
            return JsonResponse({'success': False,
                                 'message': "Aucune prestation visée."}, status=400)
        records = list(MedicineRecord.objects.filter(id__in=ids))
        if not records:
            return JsonResponse({'success': False,
                                 'message': "Prestations introuvables."}, status=404)
        today = timezone.localdate()
        for r in records:
            r.prescriber_paid = paid
            r.prescriber_paid_on = today if paid else None
            r.save(update_fields=['prescriber_paid', 'prescriber_paid_on'])
            log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                      module='medicine', obj=r, ip_address=get_client_ip(request))
        return JsonResponse({
            'success': True,
            'message': (f"Part prescripteur marquée « versée » ({len(records)} prestation(s))."
                        if paid else
                        f"Part prescripteur remise « en attente » ({len(records)} prestation(s))."),
        })
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)
