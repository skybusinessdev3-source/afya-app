# ====================================
# Models Accounts
# ====================================
import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class User(AbstractUser):
    class Roles(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrateur système'
        DIRECTOR = 'DIRECTOR', 'Directeur'
        MANAGER = 'MANAGER', 'Gestionnaire'
        ASSISTANT_MANAGER = 'ASSISTANT_MANAGER', 'Assistant manager'
        DOCTOR = 'DOCTOR', 'Médecin'
        LAB_TECH = 'LAB_TECH', 'Technicien de laboratoire'
        PHARMACIST = 'PHARMACIST', 'Pharmacien'
        PHYSIOTHERAPIST = 'PHYSIOTHERAPIST', 'Kinésithérapeute'
        STAFF = 'STAFF', 'Personnel autorisé'

    role = models.CharField(max_length=30, choices=Roles.choices, default=Roles.STAFF)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    # Force le changement de mot de passe à la première connexion (compte créé par invitation)
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class RegistrationCode(TimeStampedModel):
    """
    Remplace le 'code dans un fichier Excel/JSON' (cf. cahier des charges §17.1).
    Codes temporaires, à durée limitée, stockés en base et audités.
    """
    code = models.CharField(max_length=64, unique=True, editable=False)
    role = models.CharField(max_length=30, choices=User.Roles.choices)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='codes_created')
    used_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='registration_code_used')
    expires_at = models.DateTimeField()
    max_uses = models.PositiveSmallIntegerField(default=1)
    use_count = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_urlsafe(16)  # code aléatoire sécurisé
        super().save(*args, **kwargs)

    def is_valid(self):
        return (
            self.is_active
            and self.use_count < self.max_uses
            and timezone.now() < self.expires_at
        )

    def __str__(self):
        return f"Code {self.role} ({'valide' if self.is_valid() else 'invalide'})"