from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.settings_app.models import ExchangeRate, Staff
from apps.patients.models import Patient

DEFAULT_RATE = Decimal('2250')  # taux de secours si aucun taux configuré (1$ = 2250 FC)


def get_current_rate() -> Decimal:
    """Taux actif en base, sinon taux par défaut du cahier des charges."""
    rate = ExchangeRate.current_rate(ExchangeRate.USD, ExchangeRate.FC)
    return rate if rate is not None else DEFAULT_RATE


class CurrencyAmountMixin(models.Model):
    """
    Tout objet 'possédant un montant' hérite de ça :
    l'historique financier est figé au moment de l'enregistrement.
    """
    class Currencies(models.TextChoices):
        USD = 'USD', 'Dollar ($)'
        FC = 'FC', 'Franc congolais (FC)'

    REFERENCE_CURRENCY = Currencies.USD  # la comptabilité interne est en $

    amount_original = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Montant")
    currency_original = models.CharField(max_length=3, choices=Currencies.choices, default=Currencies.USD)
    rate_used = models.DecimalField(max_digits=12, decimal_places=4, editable=False,
                                    verbose_name="Taux utilisé")
    amount_usd = models.DecimalField(max_digits=14, decimal_places=2, editable=False,
                                     verbose_name="Montant ($)")

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.currency_original == self.Currencies.USD:
            self.rate_used = Decimal('1')
            self.amount_usd = self.amount_original
        else:  # FC → conversion avec le taux du jour
            self.rate_used = get_current_rate()
            self.amount_usd = (self.amount_original / self.rate_used).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)


class Invoice(TimeStampedModel, CurrencyAmountMixin):
    """Facture — montant dû par un patient (ou générique si patient=None)."""

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Ouverte'
        PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partiellement payée'
        PAID = 'PAID', 'Soldée'
        CANCELLED = 'CANCELLED', 'Annulée'

    reference = models.CharField(max_length=30, unique=True, editable=False)
    patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.PROTECT,
                                related_name='invoices')
    label = models.CharField(max_length=255, verbose_name="Libellé")  # ex: "Séances kiné x5"
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    date = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='cancelled_invoices')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    # Créance (solde restant dû) : None = pas encore décidé, True = stockée
    # dans les créances, False = refusée (toutes les créances ne sont pas importantes)
    debt_tracked = models.BooleanField(null=True, blank=True, default=None,
                                       verbose_name="Créance stockée")

    class Meta:
        ordering = ['-date']

    def save(self, *args, **kwargs):
        if not self.reference:
            date_part = (self.date or timezone.localdate()).strftime('%Y%m%d')
            count = Invoice.objects.filter(reference__startswith=f'FAC-{date_part}').count()
            self.reference = f'FAC-{date_part}-{count + 1:03d}'
        super().save(*args, **kwargs)

    @property
    def amount_paid_usd(self):
        return sum(p.amount_usd for p in self.payments.filter(status=Payment.Status.VALID))

    @property
    def balance_usd(self):
        return self.amount_usd - self.amount_paid_usd

    def delete(self, *args, **kwargs):
        raise ValidationError("Une facture ne se supprime pas — utilisez cancel().")

    def cancel(self, user, reason):
        if self.status == self.Status.CANCELLED:
            raise ValidationError("Facture déjà annulée.")
        self.status = self.Status.CANCELLED
        self.cancelled_by = user
        self.cancelled_at = timezone.now()
        self.cancel_reason = reason
        self.save()
        # → on appelera log_event() ici (traçabilité) au moment des vues/services

    def __str__(self):
        return f"{self.reference} — {self.patient or 'Générique'} ({self.get_status_display()})"


class Payment(TimeStampedModel, CurrencyAmountMixin):
    """Paiement reçu — lié à une facture (ou versement global si facture=None)."""

    class Status(models.TextChoices):
        VALID = 'VALID', 'Valide'
        CANCELLED = 'CANCELLED', 'Annulé'

    class Methods(models.TextChoices):
        CASH = 'CASH', 'Espèces'
        MOBILE_MONEY = 'MOBILE_MONEY', 'Mobile Money'
        BANK = 'BANK', 'Virement bancaire'

    invoice = models.ForeignKey(Invoice, null=True, blank=True, on_delete=models.PROTECT,
                                related_name='payments')
    method = models.CharField(max_length=20, choices=Methods.choices, default=Methods.CASH)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VALID)
    date = models.DateField(default=timezone.localdate)
    received_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='payments_received')
    cancelled_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='cancelled_payments')
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    def clean(self):
        if self.invoice and self.invoice.status == Invoice.Status.CANCELLED:
            raise ValidationError("Impossible de payer une facture annulée.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Un paiement ne se supprime pas — utilisez cancel().")

    def cancel(self, user, reason):
        if self.status == self.Status.CANCELLED:
            raise ValidationError("Paiement déjà annulé.")
        self.status = self.Status.CANCELLED
        self.cancelled_by = user
        self.cancelled_at = timezone.now()
        self.cancel_reason = reason
        self.save()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Mise à jour automatique du statut de la facture
        if self.invoice:
            inv = self.invoice
            if inv.balance_usd <= 0:
                inv.status = Invoice.Status.PAID
            else:
                inv.status = Invoice.Status.PARTIALLY_PAID
            if inv.amount_paid_usd == 0:
                inv.status = Invoice.Status.OPEN
            inv.save(update_fields=['status'])

    def __str__(self):
        return f"Paiement {self.amount_original} {self.currency_original} ({self.date:%d/%m/%Y})"


class Expense(TimeStampedModel, CurrencyAmountMixin):
    """Dépense : transport cleaner, A.G, poubelle, autre..."""

    label = models.CharField(max_length=150, verbose_name="Libellé")
    person = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                               verbose_name="Personne concernée")
    person_other = models.CharField(max_length=100, blank=True, verbose_name="Autre personne")
    date = models.DateField(default=timezone.localdate)
    observation = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.label} — {self.amount_original} {self.currency_original}"


class Debt(TimeStampedModel):
    """
    Dette d'un patient envers le centre.
    Source : solde impayé d'une facture. remaining_usd mis à jour par les paiements.
    """
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'En cours'
        SETTLED = 'SETTLED', 'Soldée'
        WAIVED = 'WAIVED', 'Abandonnée'

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='debts')
    invoice = models.OneToOneField(Invoice, null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='debt')
    amount_usd = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Montant initial ($)")
    remaining_usd = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Reste dû ($)")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Dette {self.patient} — reste: {self.remaining_usd}$"