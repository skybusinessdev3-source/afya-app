from django.db import models

from apps.core.models import TimeStampedModel
from apps.settings_app.models import Company


class Patient(TimeStampedModel):
    """Dossier patient — identité et suivi des séances."""

    class Sex(models.TextChoices):
        M = 'M', 'Masculin'
        F = 'F', 'Féminin'

    class DayPattern(models.TextChoices):
        EVEN = 'EVEN', 'Jours pairs'
        ODD = 'ODD', 'Jours impairs'
        ALL = 'ALL', 'Tous les jours'

    last_name = models.CharField(max_length=100, verbose_name="Nom")            # Nom*
    middle_name = models.CharField(max_length=100, blank=True, verbose_name="Post-nom")
    first_name = models.CharField(max_length=100, verbose_name="Prénom")        # Prénom*
    sex = models.CharField(max_length=1, choices=Sex.choices, verbose_name="Sexe")  # Sexe*
    birth_place = models.CharField(max_length=100, blank=True, verbose_name="Lieu de naissance")
    birth_date = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='patients', verbose_name="Entreprise")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Téléphone")
    day_pattern = models.CharField(max_length=10, choices=DayPattern.choices,
                                   default=DayPattern.ALL, verbose_name="Jour de venue")
    sessions_prescribed = models.PositiveIntegerField(default=0,
                                                      verbose_name="Séances prescrites")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['last_name', 'middle_name', 'first_name']),
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        parts = [self.last_name, self.middle_name, self.first_name]
        return ' '.join(p for p in parts if p)

    @property
    def full_name(self):
        return str(self)

    @property
    def sessions_done(self):
        return self.sessions.filter(status='DONE').count()

    @property
    def sessions_remaining(self):
        return max(self.sessions_prescribed - self.sessions_done, 0)