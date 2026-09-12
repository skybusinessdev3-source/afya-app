from django.db import models


class TimeStampedModel(models.Model):
    """Ajoute created_at / updated_at à tous les modèles."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True