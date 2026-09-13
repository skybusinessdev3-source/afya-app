import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.patients.models import Patient
from apps.settings_app.models import Staff
from .models import Appointment


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')


@login_required
def calendar_page(request):
    context = {
        'page_title': 'Rendez-vous',
        'doctors': Staff.objects.filter(is_active=True, title='DOCTOR'),
    }
    return render(request, 'appointments/calendar.html', context)


@login_required
def month_appointments(request):
    """RDV d'un mois pour le calendrier : ?mois=2026-09"""
    month_str = request.GET.get('mois', '')
    try:
        year, month = map(int, month_str.split('-'))
    except (ValueError, AttributeError):
        today = timezone.localdate()
        year, month = today.year, today.month

    records = Appointment.objects.filter(
        datetime__year=year, datetime__month=month,
        status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
    ).select_related('patient', 'doctor').order_by('datetime')

    days = {}
    for a in records:
        key = a.datetime.strftime('%Y-%m-%d')
        days.setdefault(key, []).append({
            'id': a.id,
            'time': a.datetime.strftime('%H:%M'),
            'patient': a.patient.full_name,
            'doctor': str(a.doctor) if a.doctor else '—',
            'motif': a.motif,
            'status': a.status,
        })
    return JsonResponse({'days': days})


@login_required
@require_POST
@transaction.atomic
def appointment_create(request):
    try:
        data = json.loads(request.body)
        patient = Patient.objects.get(pk=data['patient_id'], is_active=True)

        appointment = Appointment.objects.create(
            patient=patient,
            doctor_id=data.get('doctor_id') or None,  # None → Dr. Directeur (config)
            motif=data['motif'].strip(),
            datetime=data['datetime'],                # format "YYYY-MM-DDTHH:MM"
            remind_days_before=int(data.get('remind_days_before', 1)),
            alarm=bool(data.get('alarm', True)),
            notes=data.get('notes', ''),
            created_by=request.user,
        )
        log_event(user=request.user, action=AuditLog.Actions.CREATE,
                  module='appointments', obj=appointment, ip_address=get_client_ip(request))

        appointment.refresh_from_db()  # datetime rechargé comme objet date (plus une chaîne)
        return JsonResponse({
            'success': True,
            'message': f"Rendez-vous créé pour {patient.full_name} "
                       f"({appointment.datetime:%d/%m/%Y %H:%M}).",
        })
    except (Patient.DoesNotExist, KeyError):
        return JsonResponse({'success': False, 'message': "Patient introuvable."}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f"Données invalides : {e}"}, status=400)


@login_required
@require_POST
@transaction.atomic
def appointment_cancel(request, pk):
    appointment = Appointment.objects.get(pk=pk)
    appointment.status = Appointment.Status.CANCELLED
    appointment.save(update_fields=['status'])
    log_event(user=request.user, action=AuditLog.Actions.CANCEL,
              module='appointments', obj=appointment, ip_address=get_client_ip(request))
    return JsonResponse({'success': True, 'message': 'Rendez-vous annulé.'})