from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.accounts.models import User
from apps.patients.models import Patient


class PharmacyProduct(TimeStampedModel):
    """Produit pharmaceutique — le stock est CALCULÉ, jamais saisi."""

    name = models.CharField(max_length=150, unique=True)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Prix unitaire ($)")
    price_fc = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Prix unitaire (FC)")
    expiry_date = models.DateField(null=True, blank=True, verbose_name="Date d'expiration")
    observation = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    @property
    def stock_available(self):
        """Somme de tous les mouvements — source de vérité unique (§11)."""
        ins = self.movements.filter(movement_type=StockMovement.Type.IN, status='VALID').aggregate(
            total=models.Sum('quantity'))['total'] or 0
        outs = self.movements.filter(movement_type=StockMovement.Type.OUT, status='VALID').aggregate(
            total=models.Sum('quantity'))['total'] or 0
        return ins - outs

    def __str__(self):
        return f"{self.name} (stock: {self.stock_available})"


class StockMovement(TimeStampedModel):
    """Toute entrée/sortie de stock est un mouvement tracé — jamais supprimé (§11)."""

    class Type(models.TextChoices):
        IN = 'IN', 'Entrée'
        OUT = 'OUT', 'Sortie'

    class Status(models.TextChoices):
        VALID = 'VALID', 'Valide'
        CANCELLED = 'CANCELLED', 'Annulé'

    product = models.ForeignKey(PharmacyProduct, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=3, choices=Type.choices)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=150, blank=True, verbose_name="Motif")
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VALID)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    sale = models.OneToOneField('PharmacySale', null=True, blank=True,
                                on_delete=models.PROTECT, related_name='movements')

    class Meta:
        ordering = ['-date']

    def clean(self):
        # Anti stock négatif : on vérifie AVANT d'enregistrer (§11, §23)
        if self.movement_type == self.Type.OUT and self.pk is None:
            if self.quantity > self.product.stock_available:
                raise ValidationError(
                    f"Stock insuffisant pour « {self.product.name} » "
                    f"(disponible: {self.product.stock_available}, demandé: {self.quantity})"
                )

    def delete(self, *args, **kwargs):
        raise ValidationError("Un mouvement de stock ne se supprime pas — annulez-le.")

    def __str__(self):
        return f"{self.get_movement_type_display()} {self.quantity} × {self.product.name}"



class PharmacySale(TimeStampedModel):
    """Vente en pharmacie — crée automatiquement le mouvement de sortie."""

    patient = models.ForeignKey(Patient, null=True, blank=True, on_delete=models.SET_NULL,
                                related_name='pharmacy_sales')
    product = models.ForeignKey(PharmacyProduct, on_delete=models.PROTECT, related_name='sales')
    quantity = models.PositiveIntegerField()
    # Prix figé au moment de la vente (si le prix du produit change plus tard, la vente garde le sien)
    unit_price_usd = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    unit_price_fc = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    total_usd = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    total_fc = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    date = models.DateField(default=timezone.localdate)
    sold_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    def save(self, *args, **kwargs):
        if self.pk is None:  # uniquement à la création
            self.unit_price_usd = self.product.price_usd
            self.unit_price_fc = self.product.price_fc
            self.total_usd = self.unit_price_usd * self.quantity
            self.total_fc = self.unit_price_fc * self.quantity
        super().save(*args, **kwargs)
        if self.pk and not self.movements.exists():
            StockMovement.objects.create(
                product=self.product,
                movement_type=StockMovement.Type.OUT,
                quantity=self.quantity,
                reason=f"Vente ({self.patient or 'client comptant'})",
                date=self.date,
                created_by=self.sold_by,
            )

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"Vente {self.quantity} × {self.product.name}"