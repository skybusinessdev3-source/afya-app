import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.finance.models import Invoice, Payment
from apps.patients.models import Patient
from apps.settings_app.models import Staff
from .models import HomeCareService, HomeCarePaymentSplit, split_home_care_payment


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
def home_care_page(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    records = HomeCareService.objects.filter(
        date__gte=month_start
    ).select_related('patient', 'doctor', 'invoice').order_by('-date')

    # Splits payés par facture (la répartition = f(montant payé), jamais prescrit)
    splits_by_invoice = {}
    for s in HomeCarePaymentSplit.objects.filter(
            payment__invoice__home_care_services__in=records,
            payment__status=Payment.Status.VALID):
        inv_id = s.payment.invoice_id
        d, c = splits_by_invoice.get(inv_id, (Decimal('0'), Decimal('0')))
        splits_by_invoice[inv_id] = (d + s.doctor_amount_usd, c + s.center_amount_usd)

    records_data = []
    for r in records:
        doc, cen = splits_by_invoice.get(r.invoice_id, (Decimal('0'), Decimal('0')))
        records_data.append({'r': r, 'doc': doc, 'cen': cen})

    context = {
        'page_title': 'Soins à domicile',
        'month_label': today.strftime('%B %Y'),
        'doctors': Staff.objects.filter(is_active=True, title='DOCTOR'),
        'records_data': records_data,
    }
    return render(request, 'home_care/index.html', context)


@login_required
def patient_status(request):
    patient_id = request.GET.get('patient_id')
    service = HomeCareService.objects.filter(
        patient_id=patient_id,
        sessions_done__lt=models.F('sessions_prescribed'),
    ).select_related('invoice', 'doctor').order_by('-date').first()

    if service is None:
        return JsonResponse({'has_service': False})

    invoice = service.invoice
    payments = invoice.payments.filter(status=Payment.Status.VALID) if invoice else []
    paid = sum(p.amount_usd for p in payments)
    doc_total = Decimal('0')
    cen_total = Decimal('0')
    for s in HomeCarePaymentSplit.objects.filter(payment__in=payments):
        doc_total += s.doctor_amount_usd
        cen_total += s.center_amount_usd

    return JsonResponse({
        'has_service': True,
        'service_id': service.id,
        'doctor': str(service.doctor) if service.doctor else '—',
        'sessions_done': service.sessions_done,
        'sessions_prescribed': service.sessions_prescribed,
        'sessions_remaining': service.sessions_remaining,
        'billed': f"{invoice.amount_original} {invoice.currency_original}" if invoice else '—',
        'paid_usd': float(paid),
        'balance_usd': float(invoice.balance_usd) if invoice else 0,
        'part_doctor_paid': float(doc_total),
        'part_center_paid': float(cen_total),
    })


@login_required
@require_POST
@transaction.atomic
def home_care_create(request):
    try:
        data = json.loads(request.body)
        mode = data.get('mode', 'nouveau')

        # ============ MODE SUIVI ============
        if mode == 'session':
            service = HomeCareService.objects.select_for_update().get(pk=data['service_id'])
            if service.sessions_done >= service.sessions_prescribed:
                return JsonResponse({'success': False,
                                     'message': "Toutes les séances prescrites sont déjà effectuées."},
                                    status=400)
            service.sessions_done += 1
            service.save(update_fields=['sessions_done'])
            log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                      module='home_care', obj=service, ip_address=get_client_ip(request))

            amount_paid = Decimal(str(data.get('amount_paid', '0') or '0'))
            if amount_paid > 0:
                if not service.invoice:
                    return JsonResponse({'success': False,
                                         'message': "Cette prestation n'a pas de facture."}, status=400)
                payment = Payment.objects.create(
                    invoice=service.invoice,
                    amount_original=amount_paid,
                    currency_original=data.get('paid_currency', 'USD'),
                    received_by=request.user,
                )
                # Répartition sur le MONTANT PAYÉ (figée au taux du paiement)
                split_home_care_payment(payment)
                log_event(user=request.user, action=AuditLog.Actions.CREATE,
                          module='finance', obj=payment, ip_address=get_client_ip(request))

            return JsonResponse({
                'success': True,
                'message': f"Séance {service.sessions_done}/{service.sessions_prescribed} "
                           f"enregistrée pour {service.patient.full_name}.",
                'sessions_done': service.sessions_done,
                'sessions_remaining': service.sessions_remaining,
            })

        # ============ MODE NOUVEAU ============
        patient = Patient.objects.get(pk=data['patient_id'], is_active=True)
        amount = Decimal(str(data.get('amount', '0')))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
        currency = data.get('currency', 'USD')

        service = HomeCareService.objects.create(
            patient=patient,
            doctor_id=data.get('doctor_id') or None,
            sessions_prescribed=int(data.get('sessions_prescribed', 1) or 1),
            observation=data.get('observation', ''),
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='home_care', obj=service, ip_address=get_client_ip(request))

        invoice = Invoice.objects.create(
            patient=patient,
            label=f"Soins à domicile — {service.date:%d/%m/%Y}",
            amount_original=amount,
            currency_original=currency,
            created_by=request.user,
        )
        service.invoice = invoice
        service.save(update_fields=['invoice'])
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=invoice, ip_address=get_client_ip(request))

        amount_paid = Decimal(str(data.get('amount_paid', '0') or '0'))
        if amount_paid > 0:
            payment = Payment.objects.create(
                invoice=invoice,
                amount_original=amount_paid,
                currency_original=data.get('paid_currency', currency),
                received_by=request.user,
            )
            split_home_care_payment(payment)  # répartition sur le montant payé
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Prestation créée pour {patient.full_name} "
                       f"({service.sessions_prescribed} séances).",
        })

    except (Patient.DoesNotExist, HomeCareService.DoesNotExist, KeyError):
        return JsonResponse({'success': False, 'message': "Données introuvables."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)