import json
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.finance.models import Invoice, Payment
from apps.settings_app.models import Company
from .models import Patient


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
@require_POST
@transaction.atomic
def patient_create(request):
    """Crée un patient + (optionnel) facture d'ouverture. Retourne la fiche prête à l'emploi."""
    try:
        data = json.loads(request.body)

        for field in ('last_name', 'first_name', 'sex'):
            if not data.get(field):
                return JsonResponse({'success': False, 'message': f"Champ manquant : {field}."}, status=400)

        patient = Patient.objects.create(
            last_name=data['last_name'].strip(),
            middle_name=data.get('middle_name', '').strip(),
            first_name=data['first_name'].strip(),
            sex=data['sex'],
            birth_place=data.get('birth_place', '').strip(),
            birth_date=data.get('birth_date') or None,
            company_id=data.get('company_id') or None,
            phone=data.get('phone', '').strip(),
            day_pattern=data.get('day_pattern', 'ALL'),
            sessions_prescribed=int(data.get('sessions_prescribed', 0) or 0),
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='patients', obj=patient, ip_address=get_client_ip(request))

        # Facture d'ouverture (montant à payer initial, optionnel)
        amount = Decimal(str(data.get('amount_due', '0') or '0'))
        if amount > 0:
            invoice = Invoice.objects.create(
                patient=patient,
                label="Frais initiaux — inscription",
                amount_original=amount,
                currency_original=data.get('currency', 'USD'),
                created_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=invoice, ip_address=get_client_ip(request))

        return JsonResponse({
            'success': True,
            'message': f"Patient « {patient.full_name} » enregistré.",
            'patient': {
                'id': patient.id,
                'name': patient.full_name,
                'sex': patient.get_sex_display(),
                'phone': patient.phone or '—',
                'company': patient.company.name if patient.company else '—',
                'sessions_done': patient.sessions_done,
                'sessions_prescribed': patient.sessions_prescribed,
                'sessions_remaining': patient.sessions_remaining,
            },
        })

    except (InvalidOperation, ValueError):
        return JsonResponse({'success': False, 'message': "Données invalides."}, status=400)
    except Company.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Entreprise introuvable."}, status=400)


@login_required
def patient_list(request):
    """Liste des patients avec recherche."""
    q = request.GET.get('q', '').strip()
    if q:
        patients = Patient.objects.filter(
            Q(last_name__icontains=q) |
            Q(middle_name__icontains=q) |
            Q(first_name__icontains=q) |
            Q(phone__icontains=q),
            is_active=True,
        )
    else:
        patients = Patient.objects.filter(is_active=True)

    context = {
        'page_title': 'Patients',
        'patients': patients[:100],
        'q': q,
        'total': patients.count(),
    }
    return render(request, 'patients/list.html', context)


@login_required
def patient_detail(request, pk):
    """Fiche complète : infos + séances + factures/paiements + totaux dus."""
    patient = get_object_or_404(Patient, pk=pk, is_active=True)

    invoices = patient.invoices.prefetch_related('payments').exclude(
        status=Invoice.Status.CANCELLED)

    total_due_usd = sum(i.amount_usd for i in invoices)
    total_paid_usd = sum(
        p.amount_usd for i in invoices
        for p in i.payments.filter(status=Payment.Status.VALID)
    )

    context = {
        'page_title': patient.full_name,
        'p': patient,
        'sessions': patient.sessions.select_related('service', 'professional')[:50],
        'invoices': invoices[:30],
        'total_due_usd': total_due_usd,
        'total_paid_usd': total_paid_usd,
        'total_remaining_usd': total_due_usd - total_paid_usd,
        'companies': Company.objects.filter(is_active=True),
    }
    return render(request, 'patients/detail.html', context)

@login_required
@require_POST
@transaction.atomic
def patient_update(request, pk):
    """Modification d'un patient (identité, entreprise, séances prescrites)."""
    try:
        data = json.loads(request.body)
        p = Patient.objects.get(pk=pk, is_active=True)
        p.last_name = data.get('last_name', p.last_name).strip() or p.last_name
        p.middle_name = data.get('middle_name', p.middle_name).strip()
        p.first_name = data.get('first_name', p.first_name).strip()
        if data.get('sex') in ('M', 'F'):
            p.sex = data['sex']
        p.birth_place = data.get('birth_place', p.birth_place).strip()
        p.birth_date = data.get('birth_date') or p.birth_date
        p.phone = data.get('phone', p.phone).strip()
        p.company_id = data.get('company_id') or None
        p.day_pattern = data.get('day_pattern', p.day_pattern)
        p.sessions_prescribed = int(data.get('sessions_prescribed', p.sessions_prescribed) or 0)
        p.save()
        log_event(user=request.user, action=AuditLog.Actions.UPDATE,
                  module='patients', obj=p, ip_address=get_client_ip(request))
        return JsonResponse({'success': True, 'message': f'{p.full_name} mis à jour.'})
    except (Patient.DoesNotExist, ValueError):
        return JsonResponse({'success': False, 'message': 'Données invalides.'}, status=400)