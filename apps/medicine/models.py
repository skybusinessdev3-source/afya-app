from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.patients.models import Patient
from apps.settings_app.models import MedicineSplitConfig, PrescriberConfig, Staff
from apps.finance.models import CurrencyAmountMixin, Invoice, get_current_rate


def get_active_medicine_split(category):
    config = MedicineSplitConfig.objects.filter(
        category=category, is_active=True, effective_from__lte=timezone.now()
    ).first()
    if config:
        return config.prescriber_pct, config.center_pct
    defaults = {
        MedicineSplitConfig.Categories.GENERAL_CONSULTATION: (Decimal('20'), Decimal('80')),
        MedicineSplitConfig.Categories.GENERAL_OTHER: (Decimal('40'), Decimal('60')),
        MedicineSplitConfig.Categories.MANUAL: (Decimal('20'), Decimal('80')),
        MedicineSplitConfig.Categories.MANUAL_OTHER: (Decimal('20'), Decimal('80')),
    }
    return defaults.get(category, (Decimal('0'), Decimal('100')))


class MedicineRecord(TimeStampedModel, CurrencyAmountMixin):
    """Prestation de médecine — répartition FIGÉE à la création (comme le labo)."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'En attente'
        DONE = 'DONE', 'Effectuée'
        PAID = 'PAID', 'Payée'

    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='medicine_records')
    category = models.CharField(max_length=30, choices=MedicineSplitConfig.Categories.choices)
    prescriber_name = models.CharField(max_length=150, blank=True, verbose_name="Prescripteur")
    prescriber = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='medicine_records', verbose_name="Médecin (Staff)")
    prestation_other = models.CharField(max_length=150, blank=True, verbose_name="Précision (autre prestation)")
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DONE)
    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='medicine_records')
    prescriber_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    center_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    # Suivi du VERSEMENT de la part prescripteur (indépendant de l'encaissement patient)
    prescriber_paid = models.BooleanField(default=False, verbose_name="Part prescripteur déjà versée")
    prescriber_paid_on = models.DateField(null=True, blank=True, verbose_name="Part versée le")
    observation = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def save(self, *args, **kwargs):
        if self.pk is None:
            # 1) Conversion d'abord (sinon amount_usd est None pour les splits)
            if self.currency_original == self.Currencies.USD:
                self.rate_used = Decimal('1')
                self.amount_usd = self.amount_original
            else:
                self.rate_used = get_current_rate()
                self.amount_usd = (self.amount_original / self.rate_used).quantize(Decimal('0.01'))
            # 2) Répartition figée — config INDIVIDUELLE du médecin d'abord
            #    (tarif × % plafonné au montant facturé), sinon split global.
            config = None
            if self.prescriber_id:
                config = PrescriberConfig.objects.filter(
                    staff_id=self.prescriber_id, category=self.category, is_active=True).first()
            if config:
                part = (config.tariff_usd * config.prescriber_pct / 100).quantize(Decimal('0.01'))
                self.prescriber_amount_usd = min(part, self.amount_usd)
            else:
                prescriber_pct, center_pct = get_active_medicine_split(self.category)
                self.prescriber_amount_usd = (self.amount_usd * prescriber_pct / 100).quantize(Decimal('0.01'))
            self.center_amount_usd = self.amount_usd - self.prescriber_amount_usd
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.get_category_display()} — {self.patient} ({self.date:%d/%m/%Y})"