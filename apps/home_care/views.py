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
from apps.core.utils import can_backdate, parse_operation_date
from apps.finance.models import Invoice, Payment
from apps.finance.views import _creance_info
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
    parts_attente_count = 0
    parts_attente_total = Decimal('0')
    for r in records:
        doc, cen = splits_by_invoice.get(r.invoice_id, (Decimal('0'), Decimal('0')))
        records_data.append({'r': r, 'doc': doc, 'cen': cen})
        # Part médecin pas encore marquée « versée » (mois affiché)
        if doc > 0 and not r.doctor_paid:
            parts_attente_count += 1
            parts_attente_total += doc

    context = {
        'page_title': 'Soins à domicile',
        'month_label': today.strftime('%B %Y'),
        'today': today,
        'can_backdate': can_backdate(request.user),
        'doctors': Staff.objects.filter(is_active=True, title='DOCTOR'),
        'records_data': records_data,
        'parts_attente_count': parts_attente_count,
        'parts_attente_total': f"{parts_attente_total:.2f}".rstrip('0').rstrip('.'),
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

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

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

            cur1 = data.get('paid_currency', 'USD')
            paiements = [
                (Decimal(str(data.get('amount_paid', '0') or '0')), cur1),
                (Decimal(str(data.get('amount_paid2', '0') or '0')),
                 data.get('paid_currency2') or ('FC' if cur1 == 'USD' else 'USD')),
            ]
            paiements = [(a, c) for a, c in paiements if a > 0]
            if paiements:
                if not service.invoice:
                    return JsonResponse({'success': False,
                                         'message': "Cette prestation n'a pas de facture."}, status=400)
                for amount_paid, cur in paiements:
                    payment = Payment.objects.create(
                        invoice=service.invoice,
                        amount_original=amount_paid,
                        currency_original=cur,
                        date=op_date,
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
                'creance': _creance_info(service.invoice),
            })

        # ============ MODE NOUVEAU ============
        patient = Patient.objects.get(pk=data['patient_id'], is_active=True)
        amount = Decimal(str(data.get('amount', '0')))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
        currency = data.get('currency', 'USD')

        # Type de prestation : soins (séances) ou consultation (acte unique)
        service_type = data.get('service_type', 'SOINS')
        if service_type not in ('SOINS', 'CONSULTATION'):
            service_type = 'SOINS'
        is_consult = service_type == 'CONSULTATION'
        # Le médecin peut recevoir sa part le jour même — on le trace dès l'enregistrement
        part_deja_versee = bool(data.get('doctor_paid'))

        service = HomeCareService.objects.create(
            patient=patient,
            doctor_id=data.get('doctor_id') or None,
            service_type=service_type,
            sessions_prescribed=1 if is_consult else int(data.get('sessions_prescribed', 1) or 1),
            sessions_done=1 if is_consult else 0,
            date=op_date,
            doctor_paid=part_deja_versee,
            doctor_paid_on=op_date if part_deja_versee else None,
            observation=data.get('observation', ''),
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='home_care', obj=service, ip_address=get_client_ip(request))

        type_txt = "Consultation à domicile" if is_consult else "Soins à domicile"
        invoice = Invoice.objects.create(
            patient=patient,
            label=f"{type_txt} — {service.date:%d/%m/%Y}",
            amount_original=amount,
            currency_original=currency,
            date=op_date,
            created_by=request.user,
        )
        service.invoice = invoice
        service.save(update_fields=['invoice'])
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=invoice, ip_address=get_client_ip(request))

        cur1 = data.get('paid_currency', currency)
        paiements = [
            (Decimal(str(data.get('amount_paid', '0') or '0')), cur1),
            (Decimal(str(data.get('amount_paid2', '0') or '0')),
             data.get('paid_currency2') or ('FC' if cur1 == 'USD' else 'USD')),
        ]
        for amount_paid, cur in [(a, c) for a, c in paiements if a > 0]:
            payment = Payment.objects.create(
                invoice=invoice,
                amount_original=amount_paid,
                currency_original=cur,
                date=op_date,
                received_by=request.user,
            )
            split_home_care_payment(payment)  # répartition sur le montant payé
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=payment, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': (f"Consultation enregistrée pour {patient.full_name}."
                        if is_consult else
                        f"Prestation créée pour {patient.full_name} "
                        f"({service.sessions_prescribed} séances)."),
            'creance': _creance_info(invoice),
        })

    except (Patient.DoesNotExist, HomeCareService.DoesNotExist, KeyError):
        return JsonResponse({'success': False, 'message': "Données introuvables."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)


@login_required
@require_POST
@transaction.atomic
def home_doctor_paid(request):
    """Marque la part médecin d'une ou plusieurs prestations comme versée
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
        records = list(HomeCareService.objects.filter(id__in=ids))
        if not records:
            return JsonResponse({'success': False,
                                 'message': "Prestations introuvables."}, status=404)
        today = timezone.localdate()
        for r in records:
            r.doctor_paid = paid
            r.doctor_paid_on = today if paid else None
            r.save(update_fields=['doctor_paid', 'doctor_paid_on'])
            log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                      module='home_care', obj=r, ip_address=get_client_ip(request))
        return JsonResponse({
            'success': True,
            'message': (f"Part médecin marquée « versée » ({len(records)} prestation(s))."
                        if paid else
                        f"Part médecin remise « en attente » ({len(records)} prestation(s))."),
        })
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)