"""
Suppression ciblée de ventes pharmacie et/ou de dépenses (correction d'erreurs de saisie).

Usage :
    python manage.py supprimer_ventes_depenses                 # liste les ventes & dépenses récentes (ne supprime rien)
    python manage.py supprimer_ventes_depenses --vente 12      # supprime le PANIER de la vente #12 (stock restauré)
    python manage.py supprimer_ventes_depenses --vente 12 13   # plusieurs paniers
    python manage.py supprimer_ventes_depenses --depense 4     # supprime la dépense #4
    python manage.py supprimer_ventes_depenses --toutes-ventes --toutes-depenses
    python manage.py supprimer_ventes_depenses --vente 12 --yes   # sans confirmation

Une « vente » en caisse = un panier : N lignes PharmacySale + N sorties de stock
+ 1 facture « Pharmacie — ... » + son paiement. Le script supprime le panier
ENTIER (retrouvé par vendeur + instant), donc le stock remonte automatiquement
et la recette disparaît des rapports. Les ACHATS (entrées de stock) ne sont
jamais touchés.

⚠️  IRRÉVERSIBLE — en cas de doute, sauvegarde d'abord :
    sudo -u postgres pg_dump afya_db > /root/backup_avant_suppression.sql
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.finance.models import Expense, Invoice, Payment
from apps.pharmacy.models import PharmacySale, StockMovement

FENETRE = timedelta(seconds=10)  # les lignes d'un même panier sont créées dans la même seconde


def _panier(sale):
    """Toutes les lignes du même panier (même vendeur, même patient, même instant)."""
    return PharmacySale.objects.filter(
        sold_by=sale.sold_by, patient=sale.patient,
        created_at__gte=sale.created_at - FENETRE,
        created_at__lte=sale.created_at + FENETRE)


def _factures_du_panier(lignes):
    """Facture(s) « Pharmacie — ... » créée(s) dans le même instant par le même vendeur."""
    pks = set()
    for s in lignes:
        for inv in Invoice.objects.filter(
                label__startswith='Pharmacie', created_by=s.sold_by,
                created_at__gte=s.created_at - FENETRE,
                created_at__lte=s.created_at + FENETRE):
            pks.add(inv.pk)
    return Invoice.objects.filter(pk__in=pks)


class Command(BaseCommand):
    help = "Supprime des ventes pharmacie (panier entier, stock restauré) et/ou des dépenses."

    def add_arguments(self, parser):
        parser.add_argument('--vente', type=int, nargs='+', default=[],
                            help="ID(s) de vente — le panier entier est supprimé.")
        parser.add_argument('--depense', type=int, nargs='+', default=[],
                            help="ID(s) de dépense à supprimer.")
        parser.add_argument('--toutes-ventes', action='store_true',
                            help="Supprimer TOUTES les ventes (les achats/stock entrant restent).")
        parser.add_argument('--toutes-depenses', action='store_true',
                            help="Supprimer TOUTES les dépenses.")
        parser.add_argument('--yes', action='store_true',
                            help="Ne pas demander de confirmation.")

    # ------------------------------------------------------------------ liste
    def _lister(self):
        self.stdout.write("\n=== 20 dernières VENTES ===")
        for s in PharmacySale.objects.select_related('product', 'patient', 'sold_by')[:20]:
            self.stdout.write(
                f"  Vente #{s.id} | {s.date:%d/%m/%Y} | {s.quantity} × {s.product.name} "
                f"| {s.patient or 'client comptant'} | par {s.sold_by or '?'}")
        self.stdout.write("\n=== 20 dernières DÉPENSES ===")
        for e in Expense.objects.order_by('-date', '-id')[:20]:
            self.stdout.write(
                f"  Dépense #{e.id} | {e.date:%d/%m/%Y} | {e.label} "
                f"| {e.amount_original} {e.currency_original}")
        self.stdout.write("\nPour supprimer : --vente ID  ou  --depense ID")

    # ------------------------------------------------------------------ handle
    def handle(self, *args, **options):
        vente_ids = options['vente']
        depense_ids = options['depense']

        if not (vente_ids or depense_ids or options['toutes_ventes'] or options['toutes_depenses']):
            self._lister()
            return

        # --- Rassembler les ventes (paniers entiers) ---
        if options['toutes_ventes']:
            ventes = PharmacySale.objects.all()
            factures = Invoice.objects.filter(label__startswith='Pharmacie')
        else:
            ventes = PharmacySale.objects.none()
            for vid in vente_ids:
                s = PharmacySale.objects.filter(pk=vid).first()
                if s is None:
                    self.stderr.write(self.style.ERROR(f"Vente #{vid} introuvable — ignorée."))
                    continue
                ventes = ventes | _panier(s)
            ventes = ventes.distinct()
            factures = _factures_du_panier(ventes)

        depenses = (Expense.objects.all() if options['toutes_depenses']
                    else Expense.objects.filter(pk__in=depense_ids))
        for did in depense_ids:
            if not depenses.filter(pk=did).exists():
                self.stderr.write(self.style.ERROR(f"Dépense #{did} introuvable — ignorée."))

        nb_ventes = ventes.count()
        nb_mouvements = StockMovement.objects.filter(sale__in=ventes).count()
        nb_factures = factures.count()
        nb_paiements = Payment.objects.filter(invoice__in=factures).count()
        nb_depenses = depenses.count()

        if not (nb_ventes or nb_depenses):
            self.stdout.write("Rien à supprimer.")
            return

        # --- Aperçu ---
        self.stdout.write(self.style.WARNING("\n⚠️  Vous allez supprimer :"))
        if nb_ventes:
            self.stdout.write(f"   • Lignes de vente................ {nb_ventes}")
            self.stdout.write(f"   • Sorties de stock (stock restauré) {nb_mouvements}")
            self.stdout.write(f"   • Factures pharmacie............ {nb_factures}")
            self.stdout.write(f"   • Paiements liés................ {nb_paiements}")
            for s in ventes.select_related('product')[:10]:
                self.stdout.write(f"       - {s.date:%d/%m/%Y} : {s.quantity} × {s.product.name}")
        if nb_depenses:
            self.stdout.write(f"   • Dépenses...................... {nb_depenses}")
            for e in depenses[:10]:
                self.stdout.write(f"       - {e.date:%d/%m/%Y} : {e.label} ({e.amount_original} {e.currency_original})")
        self.stdout.write("   (Achats/entrées de stock, produits, patients : CONSERVÉS.)\n")

        if not options['yes']:
            if input("Tapez SUPPRIMER pour confirmer : ").strip() != 'SUPPRIMER':
                self.stdout.write("Annulé — rien n'a été supprimé.")
                return

        # --- Suppression (ordre imposé par les PROTECT) ---
        with transaction.atomic():
            Payment.objects.filter(invoice__in=factures).delete()      # 1) paiements
            StockMovement.objects.filter(sale__in=ventes).delete()     # 2) sorties de stock
            ventes.delete()                                            # 3) ventes
            factures.delete()                                          # 4) factures
            depenses.delete()                                          # 5) dépenses

            log_event(user=None, action=AuditLog.Actions.DELETE, module='pharmacy',
                      new_value={'commande': 'supprimer_ventes_depenses',
                                 'ventes': nb_ventes, 'factures': nb_factures,
                                 'depenses': nb_depenses})

        msg = []
        if nb_ventes:
            msg.append(f"{nb_ventes} ligne(s) de vente supprimée(s) — stock restauré")
        if nb_depenses:
            msg.append(f"{nb_depenses} dépense(s) supprimée(s)")
        self.stdout.write(self.style.SUCCESS("\n✅ " + " · ".join(msg) + "."))