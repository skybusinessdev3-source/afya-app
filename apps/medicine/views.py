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
from apps.settings_app.models import MedicineSplitConfig
from .models import MedicineRecord


def get_client_ip(request):
    x = request.META.get('HTTP_X_FORWARDED_FOR')
    return x.split(',')[0] if x else request.META.get('REMOTE_ADDR')


def _page(request, categories, title):
    today = timezone.localdate()
    month_start = today.replace(day=1)
    records = MedicineRecord.objects.filter(
        category__in=categories, date__gte=month_start
    ).select_related('patient').order_by('-date')

    pcts = {}
    for cat in categories:
        cfg = MedicineSplitConfig.objects.filter(category=cat, is_active=True).first()
        pcts[cat] = float(cfg.prescriber_pct) if cfg else 0

    return render(request, 'medicine/index.html', {
        'page_title': title,
        'month_label': today.strftime('%B %Y'),
        'today': today,
        'can_backdate': can_backdate(request.user),
        'categories': MedicineSplitConfig.Categories,
        'allowed': [c for c in MedicineSplitConfig.Categories.values if c in categories],
        'pcts': pcts,
        'records': records,
        'totals': {
            'billed': sum(r.amount_usd for r in records),
            'prescriber': sum(r.prescriber_amount_usd for r in records),
            'center': sum(r.center_amount_usd for r in records),
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
        record = MedicineRecord.objects.create(
            patient=patient,
            category=data['category'],
            date=op_date,
            prescriber_name=data.get('prescriber_name', '').strip(),
            prestation_other=data.get('prestation_other', '').strip(),
            amount_original=amount,
            currency_original=currency,
            status=MedicineRecord.Status.DONE,
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

        return JsonResponse({
            'success': True,
            'message': f"{record.get_category_display()} enregistrée pour {patient.full_name}.",
            'splits': {'prescriber': float(record.prescriber_amount_usd),
                       'center': float(record.center_amount_usd)},
        })
    except (Patient.DoesNotExist, KeyError):
        return JsonResponse({'success': False, 'message': "Patient introuvable."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)