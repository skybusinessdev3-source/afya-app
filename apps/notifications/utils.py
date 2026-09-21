import json

from django.conf import settings
from django.utils import timezone

from apps.appointments.models import Appointment
from .models import Notification, PushSubscription


def send_web_push(user, title, message, link=''):
    """
    Envoie une notification Web Push à tous les navigateurs abonnés de
    l'utilisateur — l'alarme arrive même si l'application est fermée (§14).
    Retourne le nombre d'envois réussis.
    """
    if not getattr(settings, 'VAPID_PRIVATE_KEY', ''):
        return 0
    try:
        from pywebpush import webpush
    except ImportError:
        return 0

    payload = json.dumps({'title': title, 'body': message, 'link': link})
    sent = 0
    for sub in PushSubscription.objects.filter(user=user):
        try:
            webpush(
                subscription_info={'endpoint': sub.endpoint,
                                   'keys': {'p256dh': sub.p256dh, 'auth': sub.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f"mailto:{getattr(settings, 'VAPID_ADMIN_EMAIL', 'admin@afya-app-crfmk.org')}"},
            )
            sent += 1
        except Exception:
            # Abonnement mort (navigateur désinstallé, permission retirée…) : on le supprime
            sub.delete()
    return sent


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
            send_web_push(user, 'Rappel de rendez-vous',
                          f"{appt.patient.full_name} — {appt.motif} — le {when}",
                          '/rendez-vous/')
            total += 1
        appt.reminded_at = timezone.now()
        appt.save(update_fields=['reminded_at'])

    return total