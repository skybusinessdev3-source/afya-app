"""
Mise à jour du stock pharmacie — inventaire du début septembre 2026.

Le stock étant CALCULÉ depuis les mouvements (§11), ce script ne touche
jamais un champ « stock » : il crée un MOUVEMENT D'AJUSTEMENT (entrée ou
sortie) daté au 01/09/2026 pour que le stock calculé = stock réel de
l'inventaire. Il met aussi à jour les prix et l'observation.
Les produits inexistants sont créés.

Usage : python manage.py maj_stock --settings=config.settings.production
        python manage.py maj_stock --date 2026-09-01   (autre date si besoin)
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.pharmacy.models import PharmacyProduct, StockMovement

# (nom, dosage, forme, stock réel (Reste), prix FC, prix $, observation)
# Prix None = non renseigné → on ne touche pas au prix existant.
INVENTAIRE = [
    ('CARBONEX',    '',       'Carton',    5,  None,  None,  'Moyen'),
    ('DESPAIN',     '25 mg',  'Carton',    12, None,  None,  'Normal'),
    ('COXOPAIN',    '30 mg',  'Carton',    11, 9200,  4,     'Moyen'),
    ('COXOPAIN',    '60 mg',  'Carton',    5,  9200,  4,     'Moyen'),
    ('COXOPAIN',    '90 mg',  'Carton',    5,  11500, 5,     'Moyen'),
    ('CALLOIDE',    '',       'Carton',    4,  23000, 10,    'Moyen'),
    ('FERROTONE',   '',       'Plaquette', 8,  None,  None,  'Moyen'),
    ('NEUROMED',    '140 mg', 'Carton',    1,  34500, 15,    'Bas'),
    ('PROTOQ',      '40 mg',  'Carton',    0,  None,  None,  'Rupture'),
    ('ZERICA M',    '150 mcg','Carton',    3,  32200, 14,    'Bas'),
    ('ILACAP',      '',       'Plaquette', 4,  13800, 6,     'Moyen'),
    ('THIOCROS',    '',       'Carton',    18, 13800, 6,     'Normal'),
    ('MAIGRIX',     '',       'Carton',    0,  13800, 6,     'Rupture'),
    ('NAVROX',      '',       'Carton',    13, 13800, 6,     'Normal'),
    ('LEOPARD',     '',       'Boîte',     6,  None,  None,  'Moyen'),
    ('GABEPENTINE', '600 mg', 'Plaquette', 1,  None,  None,  'Bas'),
    ('NAT B',       '',       'Plaquette', 8,  27600, 12,    'Moyen'),
    ('SHARP MAX',   '',       'Plaquette', 3,  46000, 20,    'Bas'),
    ('LYNEVIT',     '',       'Plaquette', 4,  11500, 5,     'Moyen'),
    ('ETHOMEX',     '',       'Plaquette', 2,  16100, 7,     'Bas'),
    ('EXACTIVE',    '',       'Boîte',     2,  None,  None,  'Bas'),
    ('BAUME',       '',       'Boîte',     6,  4600,  2,     'Moyen'),
    ('ORTHOGLIC',   '',       '',          17, 16100, 7,     'Normal'),
    ('CORT 80',     '',       'Carton',    0,  None,  None,  'Rupture'),
    ('CARNOREX',    '',       'Carton',    3,  None,  None,  'Bas'),
]


class Command(BaseCommand):
    help = "Ajuste le stock pharmacie sur l'inventaire du début du mois (mouvements tracés)."

    def add_arguments(self, parser):
        parser.add_argument('--date', type=str, default='2026-09-01',
                            help="Date de l'inventaire (AAAA-MM-JJ)")

    @transaction.atomic
    def handle(self, *args, **options):
        d = date.fromisoformat(options['date'])
        admin = (User.objects.filter(is_superuser=True).first()
                 or User.objects.filter(is_staff=True).first())
        motif = f"Inventaire début septembre 2026 (ajustement du {d:%d/%m/%Y})"

        self.stdout.write(self.style.WARNING(f'=== MISE À JOUR DU STOCK au {d:%d/%m/%Y} ==='))
        crees = ajustes = identiques = 0

        for nom_base, dosage, forme, reste, prix_fc, prix_usd, obs in INVENTAIRE:
            nom = f"{nom_base} {dosage}".strip()
            observation = (f"Forme: {forme} · {obs}" if forme else obs)

            produit = PharmacyProduct.objects.filter(name__iexact=nom).first()
            if produit is None:
                produit = PharmacyProduct.objects.create(
                    name=nom,
                    price_usd=Decimal(str(prix_usd)) if prix_usd else Decimal('0'),
                    price_fc=Decimal(str(prix_fc)) if prix_fc else Decimal('0'),
                    observation=observation,
                )
                crees += 1
                self.stdout.write(f'  + {nom} (créé)')

            # Prix + observation : mis à jour seulement si renseignés
            changed = []
            if prix_usd is not None and produit.price_usd != Decimal(str(prix_usd)):
                produit.price_usd = Decimal(str(prix_usd)); changed.append('prix $')
            if prix_fc is not None and produit.price_fc != Decimal(str(prix_fc)):
                produit.price_fc = Decimal(str(prix_fc)); changed.append('prix FC')
            if observation and produit.observation != observation:
                produit.observation = observation; changed.append('observation')
            if changed:
                produit.save()

            # Ajustement du stock par mouvement tracé
            actuel = produit.stock_available
            diff = reste - actuel
            if diff > 0:
                StockMovement.objects.create(
                    product=produit, movement_type=StockMovement.Type.IN,
                    quantity=diff, reason=motif, date=d, created_by=admin)
                self.stdout.write(f'  {nom:22s} stock {actuel} → {reste}  (entrée +{diff})')
                ajustes += 1
            elif diff < 0:
                StockMovement.objects.create(
                    product=produit, movement_type=StockMovement.Type.OUT,
                    quantity=-diff, reason=motif, date=d, created_by=admin)
                self.stdout.write(f'  {nom:22s} stock {actuel} → {reste}  (sortie {diff})')
                ajustes += 1
            else:
                identiques += 1
                self.stdout.write(f'  {nom:22s} stock déjà correct ({actuel})')

        self.stdout.write(self.style.SUCCESS(
            f'\nTerminé : {crees} créés, {ajustes} ajustés, {identiques} déjà corrects.'
        ))
