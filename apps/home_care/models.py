from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.finance.models import Payment
from apps.patients.models import Patient
from apps.settings_app.models import Staff, HomeCareSplitConfig


def get_active_home_care_split(service_type='SOINS'):
    """Répartition active — les consultations à domicile ont leurs propres
    pourcentages (configurés dans la page Configuration)."""
    config = HomeCareSplitConfig.objects.filter(
        is_active=True, effective_from__lte=timezone.now()
    ).first()
    if config:
        if service_type == 'CONSULTATION':
            return config.consult_doctor_pct, config.consult_center_pct
        return config.doctor_pct, config.center_pct
    return Decimal('50'), Decimal('50')


def split_home_care_payment(payment):
    """
    Répartit UN PAIEMENT reçu (§13) : la séparation se fait sur le MONTANT PAYÉ,
    jamais sur le montant prescrit. La conversion (rate_used) est déjà figée
    sur le paiement par le mixin finance.
    """
    # Soins ou consultation ? Les pourcentages diffèrent (figés à ce paiement)
    service = payment.invoice.home_care_services.first() if payment.invoice_id else None
    service_type = getattr(service, 'service_type', 'SOINS')
    doctor_pct, center_pct = get_active_home_care_split(service_type)
    doctor = (payment.amount_usd * doctor_pct / 100).quantize(Decimal('0.01'))
    return HomeCarePaymentSplit.objects.create(
        payment=payment,
        doctor_amount_usd=doctor,
        center_amount_usd=payment.amount_usd - doctor,
    )


class HomeCareService(TimeStampedModel):
    """Prestation de soins à domicile — suivi des séances et facturation."""

    class ServiceType(models.TextChoices):
        SOINS = 'SOINS', 'Soins à domicile'
        CONSULTATION = 'CONSULTATION', 'Consultation à domicile'

    service_type = models.CharField(max_length=15, choices=ServiceType.choices,
                                    default=ServiceType.SOINS, verbose_name="Type de prestation")
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT, related_name='home_care_services')
    doctor = models.ForeignKey(Staff, null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='home_care_treatments', verbose_name="Médecin traitant")
    sessions_prescribed = models.PositiveIntegerField(default=1, verbose_name="Séances prescrites")
    sessions_done = models.PositiveIntegerField(default=0, verbose_name="Séances effectuées")
    date = models.DateField(default=timezone.localdate)
    invoice = models.ForeignKey('finance.Invoice', null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='home_care_services')
    # Suivi du VERSEMENT de la part médecin (indépendant de l'encaissement patient)
    doctor_paid = models.BooleanField(default=False, verbose_name="Part médecin déjà versée")
    doctor_paid_on = models.DateField(null=True, blank=True, verbose_name="Part versée le")
    observation = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    @property
    def sessions_remaining(self):
        return max(self.sessions_prescribed - self.sessions_done, 0)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Soins domicile — {self.patient} ({self.date:%d/%m/%Y})"


class HomeCarePaymentSplit(TimeStampedModel):
    """
    Répartition FIGÉE d'un paiement de soins à domicile (§13).
    Un enregistrement par paiement — calculé sur le montant effectivement payé.
    """
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='home_care_split')
    doctor_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    center_amount_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

    def __str__(self):
        return f"Split domicile — paiement {self.payment_id}"