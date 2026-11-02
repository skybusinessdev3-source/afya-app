from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class AssistantMessage(TimeStampedModel):
    """Un message de la discussion avec l'assistant IA (historique par utilisateur)."""

    class Roles(models.TextChoices):
        USER = 'user', 'Utilisateur'
        ASSISTANT = 'assistant', 'Assistant'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='assistant_messages')
    role = models.CharField(max_length=10, choices=Roles.choices)
    content = models.TextField()
    # Texte extrait d'un fichier déposé (jamais affiché tel quel, sert de contexte à l'IA)
    context_text = models.TextField(blank=True)
    # Fichier produit par l'IA (document, tableau, image) ou déposé par l'utilisateur
    attachment = models.FileField(upload_to='assistant/files/', blank=True, null=True)
    attachment_name = models.CharField(max_length=200, blank=True)
    is_image = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user} — {self.role} — {self.content[:40]}"


class AssistantLockout(TimeStampedModel):
    """Règle anti-abus : 3 demandes hors portée → l'IA se tait 5 minutes."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='assistant_lockout')
    strikes = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    MAX_STRIKES = 3
    LOCK_MINUTES = 5

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def remaining_seconds(self):
        if not self.is_locked():
            return 0
        return int((self.locked_until - timezone.now()).total_seconds())

    def add_strike(self):
        """+1 tentative hors portée ; au 3ᵉ essai → blocage 5 minutes."""
        from datetime import timedelta
        self.strikes += 1
        if self.strikes >= self.MAX_STRIKES:
            self.locked_until = timezone.now() + timedelta(minutes=self.LOCK_MINUTES)
            self.strikes = 0
        self.save(update_fields=['strikes', 'locked_until', 'updated_at'])

    def reset(self):
        if self.strikes:
            self.strikes = 0
            self.save(update_fields=['strikes', 'updated_at'])

    def __str__(self):
        return f"Lockout {self.user} — {self.strikes} essai(s)"
