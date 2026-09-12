from django.db import models

from apps.core.models import TimeStampedModel
from apps.patients.models import Patient
from apps.settings_app.models import Staff


class Service(TimeStampedModel):
    """Catalogue des prestations : séance kiné, consultation, évaluation, autre..."""
    name = models.CharField(max_length=100, unique=True)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Prix ($)")
    price_fc = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Prix (FC)")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Session(TimeStampedModel):
    """Une séance réalisée (ou prévue) pour un patient."""

    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planifiée'
        DONE = 'DONE', 'Effectuée'
        CANCELLED = 'CANCELLED', 'Annulée'

    class Motif(models.TextChoices):
        KINE = 'KINE', 'Séance kiné'
        CONSULTATION = 'CONSULTATION', 'Consultation'
        EVALUATION = 'EVALUATION', 'Évaluation'
        LABORATORY = 'LABORATORY', 'Laboratoire'
        OTHER = 'OTHER', 'Autre'

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='sessions')
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='sessions')
    motif = models.CharField(max_length=20, choices=Motif.choices, default=Motif.KINE)
    motif_other = models.CharField(max_length=150, blank=True, verbose_name="Précision (autre)")
    professional = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='sessions', verbose_name="Professionnel")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DONE)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['patient', '-date'])]

    def __str__(self):
        return f"{self.patient} — {self.get_motif_display()} ({self.date:%d/%m/%Y})"