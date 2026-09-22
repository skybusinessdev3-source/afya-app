import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.core.utils import can_backdate, parse_operation_date
from apps.finance.models import Expense, Invoice, Payment
from apps.finance.views import _creance_info
from apps.patients.models import Patient
from apps.settings_app.models import Company, Staff
from .models import Service, Session


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
def centre_day(request):
    today = timezone.localdate()
    sessions_today = Session.objects.filter(date=today).select_related('patient', 'service')
    context = {
        'page_title': f"Centre — {today:%d/%m/%Y}",
        'today': today,
        'sessions_today': sessions_today,
        'count_today': sessions_today.count(),
        'services': Service.objects.filter(is_active=True),
        'staff_list': Staff.objects.filter(is_active=True),
        'companies': Company.objects.filter(is_active=True),
        'expenses_today': Expense.objects.filter(date=today),
        'expenses_total_usd': sum(e.amount_usd for e in Expense.objects.filter(date=today)),
        'can_backdate': can_backdate(request.user),
    }
    return render(request, 'centre/day.html', context)


@login_required
def patient_search(request):
    """Recherche instantanée (AJAX) : nom, post-nom, prénom ou téléphone."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})

    patients = Patient.objects.filter(
        Q(last_name__icontains=q) |
        Q(middle_name__icontains=q) |
        Q(first_name__icontains=q) |
        Q(phone__icontains=q),
        is_active=True,
    )[:8]

    from apps.reports.services import _factures_centre, _seances_payees, _fmt_seances
    fin = _factures_centre([p.id for p in patients])
    results = []
    for p in patients:
        payees = _seances_payees(fin[p.id]['due'], fin[p.id]['paid'],
                                 p.sessions_prescribed)
        results.append({
            'id': p.id,
            'name': p.full_name,
            'sex': p.get_sex_display(),
            'phone': p.phone or '—',
            'company': p.company.name if p.company else '—',
            'sessions_done': p.sessions_done,
            'sessions_prescribed': p.sessions_prescribed,
            'sessions_remaining': p.sessions_remaining,
            'sessions_paid': _fmt_seances(payees),   # avance (None si non calculable)
        })
    return JsonResponse({'results': results})


@login_required
@require_POST
@transaction.atomic
def register_session(request):
    """
    Enregistre une séance du jour + (optionnel) paiement sur la facture du patient.
    - La facture représente le MONTANT DÛ (pas le montant payé)
    - Le paiement s'ajoute à la facture ouverte du patient
    - Le reste dû est calculé par conversion (taux figé) si devise différente
    """
    try:
        data = json.loads(request.body)
        patient = Patient.objects.get(pk=data['patient_id'], is_active=True)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        # --- Séance ---
        session = Session.objects.create(
            patient=patient,
            service_id=data.get('service_id') or None,
            motif=data.get('motif', 'KINE'),
            motif_other=data.get('motif_other', ''),
            professional_id=data.get('professional_id') or None,
            date=op_date,
            status=Session.Status.DONE,
            notes=data.get('notes', ''),
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='centre', obj=session, ip_address=get_client_ip(request))

        # --- Paiements (1 ou 2 devises — paiement mixte $ + FC) ---
        cur1 = data.get('currency', 'USD')
        paiements = [
            (Decimal(str(data.get('amount_paid', '0') or '0')), cur1),
            (Decimal(str(data.get('amount_paid2', '0') or '0')),
             data.get('currency2') or ('FC' if cur1 == 'USD' else 'USD')),
        ]
        paiements = [(a, c) for a, c in paiements if a > 0]
        invoice = None
        if paiements:
            # 1) Cherche la facture ouverte du patient
            invoice = patient.invoices.filter(
                status__in=[Invoice.Status.OPEN, Invoice.Status.PARTIALLY_PAID]
            ).order_by('date', 'pk').first()

            # 2) Sinon, crée une facture du MONTANT DÛ (prix du service)
            if invoice is None:
                service = Service.objects.filter(pk=data['service_id']).first() if data.get('service_id') else None
                if service:
                    due_amount, due_currency = service.price_usd, 'USD'
                    label = f"{service.name} — {op_date:%d/%m/%Y}"
                else:
                    due_amount, due_currency = paiements[0][0], paiements[0][1]
                    label = f"{session.get_motif_display()} — {op_date:%d/%m/%Y}"
                invoice = Invoice.objects.create(
                    patient=patient,
                    label=label,
                    amount_original=due_amount,
                    currency_original=due_currency,
                    date=op_date,
                    created_by=request.user,
                )
                log_event(user=request.user, action=AuditLog.Actions.CREATE,
                          module='finance', obj=invoice, ip_address=get_client_ip(request))

            # 3) Chaque paiement s'ajoute à la MÊME facture (conversion auto si FC)
            for amount, currency in paiements:
                payment = Payment.objects.create(
                    invoice=invoice,
                    amount_original=amount,
                    currency_original=currency,
                    date=op_date,
                    received_by=request.user,
                )
                log_event(user=request.user, action=AuditLog.Actions.CREATE,
                          module='finance', obj=payment, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Séance enregistrée pour {patient.full_name}",
            'sessions_done': patient.sessions_done,
            'sessions_remaining': patient.sessions_remaining,
            'creance': _creance_info(invoice) if paiements else None,
        })

    except (Patient.DoesNotExist, KeyError):
        return JsonResponse({'success': False, 'message': "Patient introuvable."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)