from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.patients.models import Patient
from apps.settings_app.models import Staff, HomeCareSplitConfig
from apps.finance.models import CurrencyAmountMixin, Invoice, get_current_rate


def get_active_home_care_split():
    config = HomeCareSplitConfig.objects.filter(
        is_active=True, effective_from__lte=timezone.now()
    ).first()
    if config:
        return config.doctor_pct, config.center_pct
    return Decimal('50'), Decimal('50')  # à ajuster selon les vraies règles du centre


class HomeCareService(TimeStampedModel, CurrencyAmountMixin):
    """Prestation de soins à domicile — répartition FIGÉE à la création (§13)."""

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='home_care_services')
    doctor = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='home_care_treatments', verbose_name="Médecin traitant")
    sessions_prescribed = models.PositiveIntegerField(default=1, verbose_name="Séances prescrites")
    sessions_done = models.PositiveIntegerField(default=0, verbose_name="Séances effectuées")
    date = models.DateField(default=timezone.localdate)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='home_care_services')
    # --- Répartition historisée ---
    doctor_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    center_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    observation = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def sessions_remaining(self):
        return max(self.sessions_prescribed - self.sessions_done, 0)

    def save(self, *args, **kwargs):
        if self.pk is None:
            # 1) Conversion d'abord
            if self.currency_original == self.Currencies.USD:
                self.rate_used = Decimal('1')
                self.amount_usd = self.amount_original
            else:
                self.rate_used = get_current_rate()
                self.amount_usd = (self.amount_original / self.rate_used).quantize(Decimal('0.01'))

            # 2) Répartition figée (§13)
            doctor_pct, center_pct = get_active_home_care_split()
            self.doctor_amount_usd = (self.amount_usd * doctor_pct / 100).quantize(Decimal('0.01'))
            self.center_amount_usd = self.amount_usd - self.doctor_amount_usd
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Soins domicile — {self.patient} ({self.date:%d/%m/%Y})"