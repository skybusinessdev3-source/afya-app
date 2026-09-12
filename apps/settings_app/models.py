from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel
from apps.accounts.models import User


class CenterConfig(TimeStampedModel):
    """Configuration générale — modèle 'singleton' (une seule ligne, id=1)."""

    name = models.CharField(max_length=150, verbose_name="Nom du centre")
    logo = models.ImageField(upload_to='center/', blank=True, null=True)
    address = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    default_doctor = models.ForeignKey(
        'Staff', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='default_doctor_config',
        verbose_name="Médecin directeur (par défaut)",
    )

    class Meta:
        verbose_name = "Configuration du centre"

    def save(self, *args, **kwargs):
        self.pk = 1  # force le singleton
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Company(TimeStampedModel):
    """Entreprises (partenaires / employeurs des patients)."""

    name = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Staff(TimeStampedModel):
    """Docteurs et personnel du centre (Dr Rémy KAWELE, laborantins, A.G, cleaner...)."""

    class Titles(models.TextChoices):
        DOCTOR = 'DOCTOR', 'Docteur'
        LAB_TECH = 'LAB_TECH', 'Laborantin'
        ASSISTANT_MANAGER = 'ASSISTANT_MANAGER', 'Assistant Gestionnaire'
        CLEANER = 'CLEANER', 'Cleaner'
        OTHER = 'OTHER', 'Autre'

    class Sex(models.TextChoices):
        M = 'M', 'Masculin'
        F = 'F', 'Féminin'

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    sex = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    title = models.CharField(max_length=30, choices=Titles.choices)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.get_title_display()} {self.last_name} {self.first_name}"


class ExchangeRate(TimeStampedModel):
    """
    Historique des taux de change. On ne MODIFIE jamais un taux passé :
    on crée une nouvelle ligne (versionnage), cf. cahier des charges §10.1.
    """
    USD = 'USD'
    FC = 'FC'
    CURRENCY_CHOICES = [(USD, 'Dollar ($)'), (FC, 'Franc congolais (FC)')]

    currency_from = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=USD)
    currency_to = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default=FC)
    rate = models.DecimalField(max_digits=12, decimal_places=4)  # ex: 2250.0000
    effective_from = models.DateTimeField(verbose_name="Effectif à partir de")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-effective_from']
        indexes = [models.Index(fields=['currency_from', 'currency_to', '-effective_from'])]

    def clean(self):
        if self.currency_from == self.currency_to:
            raise ValidationError("Les deux devises doivent être différentes.")
        if self.rate <= 0:
            raise ValidationError("Le taux doit être positif.")

    def __str__(self):
        return f"1 {self.currency_from} = {self.rate} {self.currency_to} ({self.effective_from:%d/%m/%Y})"

    @classmethod
    def current_rate(cls, currency_from=USD, currency_to=FC):
        """Retourne le taux actuellement actif, ou None."""
        rate = cls.objects.filter(
            currency_from=currency_from,
            currency_to=currency_to,
            is_active=True,
            effective_from__lte=models.functions.Now(),
        ).first()
        return rate.rate if rate else None
    
class LabExam(TimeStampedModel):
    """Catalogue des examens de laboratoire."""

    name = models.CharField(max_length=150, unique=True)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Prix ($)")
    price_fc = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Prix (FC)")
    observation = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class LabSplitConfig(TimeStampedModel):
    """
    Répartition laboratoire (cf. §12.1) — versionnée comme le taux.
    Défaut : 20 % prescripteur ; sur les 80 % restants : 60 % équipe labo, 40 % centre.
    """
    prescriber_pct = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="% prescripteur")
    lab_team_pct = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="% équipe labo (du restant)")
    center_pct = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="% centre (du restant)")
    effective_from = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-effective_from']

    def clean(self):
        if not (0 <= self.prescriber_pct <= 100):
            raise ValidationError("Le % prescripteur doit être entre 0 et 100.")
        if self.lab_team_pct + self.center_pct != 100:
            raise ValidationError("Équipe labo + centre doivent totaliser exactement 100 %.")

    def __str__(self):
        return (f"Labo: {self.prescriber_pct}% prescripteur / "
                f"{self.lab_team_pct}% équipe / {self.center_pct}% centre")


class HomeCareSplitConfig(TimeStampedModel):
    """Répartition soins à domicile : part médecin traitant + part centre = 100 %."""
    doctor_pct = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="% médecin traitant")
    center_pct = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="% centre")
    effective_from = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-effective_from']

    def clean(self):
        if self.doctor_pct + self.center_pct != 100:
            raise ValidationError("Médecin + centre doivent totaliser exactement 100 %.")

    def __str__(self):
        return f"Domicile: {self.doctor_pct}% médecin / {self.center_pct}% centre"