"""Outils partagés — saisie différée (backdating) sécurisée."""
from datetime import date as date_cls, timedelta

from django.utils import timezone

# Rôles autorisés à enregistrer une opération à une date passée
BACKDATE_ROLES = {'ADMIN', 'DIRECTOR', 'MANAGER'}

# Limite de recul autorisée (en jours)
MAX_BACKDAYS = 92  # ~3 mois


def can_backdate(user):
    """Seuls les responsables (ou superuser) peuvent dater une opération dans le passé."""
    return (user is not None and user.is_authenticated
            and (user.is_superuser or user.role in BACKDATE_ROLES))


def parse_operation_date(user, raw):
    """
    Valide la date d'opération envoyée par le navigateur.
    Retourne (date, erreur) : si erreur n'est pas None, la date est None.

    Règles :
    - pas de date envoyée  → aujourd'hui (comportement normal)
    - date = aujourd'hui   → OK pour tout le monde
    - date passée          → réservé aux responsables (BACKDATE_ROLES / superuser)
    - date future          → toujours refusée
    - date > MAX_BACKDAYS  → refusée
    """
    today = timezone.localdate()
    if not raw:
        return today, None
    try:
        d = date_cls.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None, "Format de date invalide (attendu : AAAA-MM-JJ)."
    if d == today:
        return today, None
    if d > today:
        return None, "Impossible d'enregistrer une opération dans le futur."
    if not can_backdate(user):
        return None, ("Seuls les responsables peuvent enregistrer "
                      "une opération à une date passée.")
    if d < today - timedelta(days=MAX_BACKDAYS):
        return None, f"Date trop ancienne (maximum {MAX_BACKDAYS} jours en arrière)."
    return d, None
