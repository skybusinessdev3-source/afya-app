from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.patients.models import Patient
from apps.settings_app.models import Staff, LabExam, LabSplitConfig
from apps.finance.models import CurrencyAmountMixin, Invoice


def get_active_lab_split():
    config = LabSplitConfig.objects.filter(
        is_active=True, effective_from__lte=timezone.now()
    ).first()
    if config:
        return config.prescriber_pct, config.lab_team_pct, config.center_pct
    return Decimal('20'), Decimal('60'), Decimal('40')  # défaut du cahier des charges


class LaboratoryRecord(TimeStampedModel, CurrencyAmountMixin):
    """Examen de laboratoire réalisé — répartition FIGÉE à la création (§12.1)."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'En attente'
        DONE = 'DONE', 'Effectué'
        PAID = 'PAID', 'Payé'

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='lab_records')
    exam = models.ForeignKey(LabExam, on_delete=models.PROTECT, related_name='records')
    prescriber = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='lab_prescriptions')
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='lab_records')
    # --- Répartition historisée (jamais recalculée) ---
    prescriber_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    lab_team_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    center_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    observation = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def save(self, *args, **kwargs):
        if self.pk is None:
            prescriber_pct, lab_pct, center_pct = get_active_lab_split()
            self.prescriber_amount_usd = (self.amount_usd * prescriber_pct / 100).quantize(Decimal('0.01'))
            remaining = self.amount_usd - self.prescriber_amount_usd
            self.lab_team_amount_usd = (remaining * lab_pct / 100).quantize(Decimal('0.01'))
            self.center_amount_usd = remaining - self.lab_team_amount_usd
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.exam.name} — {self.patient} ({self.date:%d/%m/%Y})"