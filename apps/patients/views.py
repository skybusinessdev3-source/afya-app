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
from apps.core.utils import can_backdate
from apps.finance.models import Invoice, Payment
from apps.finance.views import _creance_info
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
            'creance': _creance_info(invoice) if amount > 0 else None,
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
    """Liste des patients avec recherche — ?archives=1 affiche les dossiers archivés (responsables)."""
    show_archives = (request.GET.get('archives') == '1') and can_backdate(request.user)
    q = request.GET.get('q', '').strip()
    base_qs = Patient.objects.filter(is_active=not show_archives)
    if q:
        patients = base_qs.filter(
            Q(last_name__icontains=q) |
            Q(middle_name__icontains=q) |
            Q(first_name__icontains=q) |
            Q(phone__icontains=q),
        )
    else:
        patients = base_qs

    context = {
        'page_title': 'Patients archivés' if show_archives else 'Patients',
        'patients': patients[:100],
        'q': q,
        'total': patients.count(),
        'archives': show_archives,
        'can_backdate': can_backdate(request.user),
    }
    return render(request, 'patients/list.html', context)


@login_required
def patient_detail(request, pk):
    """Fiche complète : infos + séances + factures/paiements + totaux dus."""
    patient = get_object_or_404(Patient, pk=pk)  # archivés inclus : dossier médical toujours consultable

    invoices = patient.invoices.prefetch_related('payments').exclude(
        status=Invoice.Status.CANCELLED)

    total_due_usd = sum(i.amount_usd for i in invoices)
    total_paid_usd = sum(
        p.amount_usd for i in invoices
        for p in i.payments.filter(status=Payment.Status.VALID)
    )

    # Avance en séances (payées) — calculée sur les factures « centre »
    from apps.reports.services import _factures_centre, _seances_payees, _fmt_seances
    fin = _factures_centre([patient.id])[patient.id]
    sessions_paid = _fmt_seances(_seances_payees(
        fin['due'], fin['paid'], patient.sessions_prescribed))

    context = {
        'page_title': patient.full_name,
        'p': patient,
        'sessions': patient.sessions.select_related('service', 'professional')[:50],
        'invoices': invoices[:30],
        'total_due_usd': total_due_usd,
        'total_paid_usd': total_paid_usd,
        'total_remaining_usd': total_due_usd - total_paid_usd,
        'sessions_paid': sessions_paid,
        'companies': Company.objects.filter(is_active=True),
        'can_backdate': can_backdate(request.user),
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

        # Ajustement financier éventuel : « Montant à payer » rempli → NOUVELLE facture
        amount = Decimal(str(data.get('amount_due', '0') or '0'))
        if amount > 0:
            invoice = Invoice.objects.create(
                patient=p,
                label="Frais — ajustement dossier patient",
                amount_original=amount,
                currency_original=data.get('currency', 'USD'),
                created_by=request.user,
            )
            log_event(user=request.user, action=AuditLog.Actions.CREATE,
                      module='finance', obj=invoice, ip_address=get_client_ip(request))

        return JsonResponse({'success': True, 'message': f'{p.full_name} mis à jour.',
                             'creance': _creance_info(invoice) if amount > 0 else None})
    except (Patient.DoesNotExist, ValueError):
        return JsonResponse({'success': False, 'message': 'Données invalides.'}, status=400)

@login_required
@require_POST
def patient_toggle_active(request, pk):
    """Archive ou restaure un patient — réservé aux responsables, tracé au journal.

    On ne supprime JAMAIS un patient (données médicales) : on archive.
    Le dossier reste consultable et le patient peut être restauré à tout moment.
    """
    if not can_backdate(request.user):
        return JsonResponse({'success': False,
                             'message': "Seuls les responsables peuvent archiver un patient."},
                            status=403)
    try:
        p = Patient.objects.get(pk=pk)
    except Patient.DoesNotExist:
        return JsonResponse({'success': False, 'message': "Patient introuvable."}, status=404)

    p.is_active = not p.is_active
    p.save(update_fields=['is_active', 'updated_at'])
    action = AuditLog.Actions.UPDATE if p.is_active else AuditLog.Actions.DELETE
    log_event(user=request.user, action=action, module='patients', obj=p,
              new_value={'archived': not p.is_active},
              ip_address=get_client_ip(request))
    msg = (f"Patient « {p.full_name} » restauré." if p.is_active
           else f"Patient « {p.full_name} » archivé (dossier conservé).")
    return JsonResponse({'success': True, 'message': msg, 'is_active': p.is_active})
