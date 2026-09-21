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
from .models import Expense, Invoice, Payment, get_current_rate


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
@require_POST
def expense_create(request):
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount', '0')))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': "Le montant doit être positif."}, status=400)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        expense = Expense.objects.create(
            label=data.get('label', '').strip(),
            person_id=data.get('person_id') or None,
            person_other=data.get('person_other', '').strip(),
            amount_original=amount,
            currency_original=data.get('currency', 'USD'),
            date=op_date,
            observation=data.get('observation', '').strip(),
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=expense, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Dépense « {expense.label} » enregistrée.",
            'id': expense.id,
        })
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)
    except Exception:
        return JsonResponse({'success': False, 'message': "Libellé obligatoire."}, status=400)


@login_required
def debts_page(request):
    """Dettes = factures non annulées dont le solde reste dû (source de vérité : Invoice)."""
    invoices = [i for i in Invoice.objects
                .exclude(status=Invoice.Status.CANCELLED)
                .select_related('patient').prefetch_related('payments')
                if i.balance_usd > 0]
    context = {
        'page_title': 'Dettes',
        'invoices': invoices,
        'total_debt': sum(i.balance_usd for i in invoices),
        'today': timezone.localdate(),
        'can_backdate': can_backdate(request.user),
    }
    return render(request, 'finance/debts.html', context)


@login_required
@require_POST
@transaction.atomic
def debt_pay(request):
    """Enregistre un paiement contre une facture impayée (régularisation de dette)."""
    try:
        data = json.loads(request.body)
        inv = Invoice.objects.get(pk=data.get('invoice_id'))
        if inv.status == Invoice.Status.CANCELLED:
            return JsonResponse({'success': False, 'message': "Facture annulée — paiement impossible."},
                                status=400)

        # Date d'opération (saisie différée — réservée aux responsables)
        op_date, err = parse_operation_date(request.user, data.get('date'))
        if err:
            return JsonResponse({'success': False, 'message': err}, status=403)

        amount = Decimal(str(data.get('amount', '0') or '0'))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': "Le montant doit être positif."}, status=400)

        # Anti trop-perçu : on compare en USD (le modèle fige le taux à l'enregistrement)
        currency = data.get('currency', 'USD')
        if currency == 'FC':
            amount_usd = (amount / get_current_rate()).quantize(Decimal('0.01'))
        else:
            amount_usd = amount
        if amount_usd > inv.balance_usd:
            return JsonResponse({'success': False,
                                 'message': f"Montant supérieur au reste dû ({inv.balance_usd} $)."},
                                status=400)

        payment = Payment.objects.create(
            invoice=inv,
            amount_original=amount,
            currency_original=currency,
            date=op_date,
            received_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='finance', obj=payment, ip_address=get_client_ip(request))

        reste = inv.balance_usd
        msg = (f"Facture {inv.reference} soldée ✔" if reste <= 0
               else f"Paiement enregistré — reste dû : {reste} $.")
        return JsonResponse({'success': True, 'message': msg, 'balance': str(reste)})

    except Invoice.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Facture introuvable."}, status=404)
    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Montant invalide."}, status=400)