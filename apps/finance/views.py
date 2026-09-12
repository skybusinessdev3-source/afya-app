import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from .models import Expense


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

        expense = Expense.objects.create(
            label=data.get('label', '').strip(),
            person_id=data.get('person_id') or None,
            person_other=data.get('person_other', '').strip(),
            amount_original=amount,
            currency_original=data.get('currency', 'USD'),
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