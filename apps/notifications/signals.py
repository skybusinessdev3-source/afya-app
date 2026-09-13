from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .utils import process_due_reminders


@receiver(user_logged_in)
def on_login_check_reminders(sender, request, user, **kwargs):
    """Double sécurité : au login, on rattrape les rappels éventuellement dus."""
    process_due_reminders()