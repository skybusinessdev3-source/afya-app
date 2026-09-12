from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.patients.models import Patient
from apps.settings_app.models import Staff, CenterConfig


class Appointment(TimeStampedModel):
    """Rendez-vous d'un patient avec un professionnel."""

    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Programmé'
        CONFIRMED = 'CONFIRMED', 'Confirmé'
        DONE = 'DONE', 'Honoré'
        CANCELLED = 'CANCELLED', 'Annulé'
        NO_SHOW = 'NO_SHOW', 'Absent'

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='appointments')
    doctor = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='appointments', verbose_name="Professionnel")
    motif = models.CharField(max_length=255, verbose_name="Motif du rendez-vous")
    datetime = models.DateTimeField(verbose_name="Date et heure")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    # Rappel : X jours avant (géré côté serveur, jamais par le navigateur — §14)
    remind_days_before = models.PositiveSmallIntegerField(default=1, verbose_name="Rappel (jours avant)")
    alarm = models.BooleanField(default=True, verbose_name="Alarme activée")
    reminded_at = models.DateTimeField(null=True, blank=True, editable=False,
                                       verbose_name="Rappel envoyé le")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['datetime']
        indexes = [models.Index(fields=['datetime', 'status'])]

    def clean(self):
        if self.datetime and self.datetime < timezone.now() and self.pk is None:
            raise ValidationError("Impossible de créer un rendez-vous dans le passé.")

    def save(self, *args, **kwargs):
        # Médecin par défaut = Dr. Directeur (configurable dans Configuration générale)
        if self.doctor is None:
            config = CenterConfig.objects.first()
            if config and config.default_doctor:
                self.doctor = config.default_doctor
        super().save(*args, **kwargs)

    @property
    def reminder_due(self):
        """True si le moment du rappel est atteint et pas encore envoyé."""
        if not self.alarm or self.reminded_at or self.status not in (
                self.Status.SCHEDULED, self.Status.CONFIRMED):
            return False
        from datetime import timedelta
        return timezone.now() >= self.datetime - timedelta(days=self.remind_days_before)

    def __str__(self):
        return f"{self.patient} ↔ {self.doctor or '—'} ({self.datetime:%d/%m/%Y %H:%M})"