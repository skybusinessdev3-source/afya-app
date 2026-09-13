from django.utils import timezone

from apps.appointments.models import Appointment
from .models import Notification


def process_due_reminders():
    """
    Cherche les RDV dont le rappel est dû (jamais dépendre du navigateur — §14)
    et crée une notification par utilisateur actif. Idempotent grâce à reminded_at.
    """
    candidates = Appointment.objects.filter(
        status__in=[Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED],
        alarm=True,
        reminded_at__isnull=True,
    ).select_related('patient')

    from apps.accounts.models import User
    users = User.objects.filter(is_active=True)

    total = 0
    for appt in candidates:
        if not appt.reminder_due:
            continue
        when = appt.datetime.strftime('%d/%m/%Y à %H:%M')
        for user in users:
            Notification.objects.create(
                user=user,
                title='Rappel de rendez-vous',
                message=f"{appt.patient.full_name} — {appt.motif} — le {when}",
                link='/rendez-vous/',
            )
            total += 1
        appt.reminded_at = timezone.now()
        appt.save(update_fields=['reminded_at'])

    return total