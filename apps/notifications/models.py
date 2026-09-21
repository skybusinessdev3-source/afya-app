from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)  # ex: '/rendez-vous/'
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at:%d/%m %H:%M}] {self.title}"

class PushSubscription(TimeStampedModel):
    """Abonnement Web Push d'un navigateur (alarme même application fermée)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='push_subscriptions')
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Abonnement push"
        verbose_name_plural = "Abonnements push"

    def __str__(self):
        return f"Push de {self.user} ({self.endpoint[:40]}…)"
