# ====================================
# Models Audit
# ====================================

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Journal d'audit — aucune modification possible via l'admin (voir plus bas)."""

    class Actions(models.TextChoices):
        CREATE = 'CREATE', 'Création'
        UPDATE = 'UPDATE', 'Modification'
        DELETE = 'DELETE', 'Suppression'
        LOGIN = 'LOGIN', 'Connexion'
        LOGIN_FAILED = 'LOGIN_FAILED', 'Échec de connexion'
        LOGOUT = 'LOGOUT', 'Déconnexion'
        EXPORT = 'EXPORT', 'Export'
        APPROVE = 'APPROVE', 'Approbation'
        CANCEL = 'CANCEL', 'Annulation'

    class Results(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Succès'
        FAILURE = 'FAILURE', 'Échec'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                             on_delete=models.SET_NULL, related_name='audit_events')
    action = models.CharField(max_length=20, choices=Actions.choices)
    module = models.CharField(max_length=50)          # ex: 'finance', 'pharmacy'
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    result = models.CharField(max_length=10, choices=Results.choices, default=Results.SUCCESS)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['module', 'action']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self):
        return f"[{self.created_at:%d/%m/%Y %H:%M}] {self.user} — {self.action} ({self.module})"