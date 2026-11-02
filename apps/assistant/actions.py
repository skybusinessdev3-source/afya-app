"""Actions d'écriture demandées à l'assistant IA — SUPERUSER UNIQUEMENT.

Principe : l'IA ne fait jamais l'action elle-même. Elle la PROPOSE ; le serveur
génère un jeton signé (django.core.signing) affiché comme carte de confirmation ;
l'action n'est exécutée qu'au clic « Confirmer » du superuser, après nouvelle
vérification de la signature (15 min de validité) et du rôle. Chaque exécution
est tracée dans le journal d'audit avec la mention « via Assistant IA ».
"""
from decimal import Decimal, InvalidOperation

from django.core import signing
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.utils import log_event

SALT = 'assistant-action-v1'
MAX_AGE = 900  # le jeton de confirmation expire après 15 minutes

ACTIONS = {
    'part_labo': "Marquer des parts prescripteur du LABORATOIRE comme versées",
    'part_medecine': "Marquer des parts prescripteur de MÉDECINE comme versées",
    'part_domicile': "Marquer des parts médecin des SOINS À DOMICILE comme versées",
    'depense': "Enregistrer une DÉPENSE",
}


def build_token(action, parametres):
    """Jeton signé transportant l'action proposée (infalsifiable côté navigateur)."""
    return signing.dumps({'a': action, 'p': parametres}, salt=SALT)


def read_token(token):
    """Valide le jeton. Lève ValueError si falsifié ou expiré."""
    try:
        data = signing.loads(token, salt=SALT, max_age=MAX_AGE)
    except signing.BadSignature:
        raise ValueError("Cette demande de confirmation est invalide ou expirée — "
                         "redemande l'action à l'assistant.")
    if data.get('a') not in ACTIONS:
        raise ValueError("Action inconnue.")
    return data['a'], data.get('p') or {}


def describe(action, p):
    """Texte lisible affiché sur la carte de confirmation."""
    if action == 'depense':
        return (f"Enregistrer la dépense « {p.get('label', '?')} » de "
                f"{p.get('montant', '?')} {p.get('devise', 'USD')}")
    ids = p.get('ids') or []
    return f"{ACTIONS[action]} — {len(ids)} élément(s) : {', '.join('#' + str(i) for i in ids[:8])}"


def execute(user, action, p):
    """Exécute l'action confirmée. Mêmes règles que les pages correspondantes.
    Retourne le message de résultat affiché dans la discussion."""
    today = timezone.localdate()

    if action == 'part_labo':
        from apps.laboratory.models import LaboratoryRecord
        records = list(LaboratoryRecord.objects.filter(id__in=p.get('ids') or []))
        if not records:
            return "Aucun examen correspondant — l'action n'a rien modifié."
        for r in records:
            r.prescriber_paid = True
            r.prescriber_paid_on = today
            r.save(update_fields=['prescriber_paid', 'prescriber_paid_on'])
            log_event(user=user, action=AuditLog.Actions.UPDATE, module='laboratory',
                      obj=r, new_value={'via': 'Assistant IA', 'prescriber_paid': True})
        return f"✅ Part prescripteur marquée « versée » pour {len(records)} examen(s) de labo."

    if action == 'part_medecine':
        from apps.medicine.models import MedicineRecord
        records = list(MedicineRecord.objects.filter(id__in=p.get('ids') or []))
        if not records:
            return "Aucun acte correspondant — l'action n'a rien modifié."
        for r in records:
            r.prescriber_paid = True
            r.prescriber_paid_on = today
            r.save(update_fields=['prescriber_paid', 'prescriber_paid_on'])
            log_event(user=user, action=AuditLog.Actions.UPDATE, module='medicine',
                      obj=r, new_value={'via': 'Assistant IA', 'prescriber_paid': True})
        return f"✅ Part prescripteur marquée « versée » pour {len(records)} acte(s) de médecine."

    if action == 'part_domicile':
        from apps.home_care.models import HomeCareService
        services = list(HomeCareService.objects.filter(id__in=p.get('ids') or []))
        if not services:
            return "Aucune prestation correspondante — l'action n'a rien modifié."
        for s in services:
            s.doctor_paid = True
            s.doctor_paid_on = today
            s.save(update_fields=['doctor_paid', 'doctor_paid_on'])
            log_event(user=user, action=AuditLog.Actions.UPDATE, module='home_care',
                      obj=s, new_value={'via': 'Assistant IA', 'doctor_paid': True})
        return f"✅ Part médecin marquée « versée » pour {len(services)} prestation(s) à domicile."

    if action == 'depense':
        from apps.finance.models import Expense
        try:
            montant = Decimal(str(p.get('montant', '0')))
        except InvalidOperation:
            return "Montant invalide — action annulée."
        devise = str(p.get('devise', 'USD')).upper()
        label = str(p.get('label', '')).strip()
        if montant <= 0 or not label or devise not in ('USD', 'FC'):
            return "Dépense invalide (libellé, montant positif et devise USD/FC requis) — annulée."
        expense = Expense.objects.create(
            label=label, amount_original=montant, currency_original=devise,
            date=today, observation='Enregistrée via Assistant IA', created_by=user)
        log_event(user=user, action=AuditLog.Actions.CREATE, module='finance',
                  obj=expense, new_value={'via': 'Assistant IA'})
        return f"✅ Dépense « {expense.label} » de {expense.amount_original} {devise} enregistrée."

    return "Action inconnue — rien n'a été modifié."
