from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.finance.models import get_current_rate
from apps.pharmacy.models import PharmacyProduct, StockMovement

# Stock officiel CRF-MK (fichier Excel du centre)
# (nom complet, prix_usd, prix_fc, quantité initiale, déjà utilisé, observation)
PRIX_A_DEFINIR = None
PRODUITS = [
    ("CARBONEX",                 None,     None,    5,  0, "Forme: Carton · Moyen"),
    ("DESPAIN 25 mg",            None,     None,   12,  0, "Forme: Carton · Moyen"),
    ("COXOPAIN 30 mg",           Decimal('4'),   Decimal('9200'),   11, 0,  "Forme: Carton · Moyen"),
    ("COXOPAIN 60 mg",           Decimal('4'),   Decimal('9200'),    5, 0,  "Forme: Carton · Moyen"),
    ("COXOPAIN 90 mg",           Decimal('5'),   Decimal('11500'),   5, 0,  "Forme: Carton · Moyen"),
    ("CALLOIDE",                 Decimal('10'),  Decimal('23000'),  12, 8,  "Forme: Carton · Moyen"),
    ("FERROTONE",                None,     None,    8,  0, "Forme: Plaquette · Moyen"),
    ("NEUROMED 140 mg",          Decimal('15'),  Decimal('34500'),   2, 1,  "Forme: Carton · Bas"),
    ("PROTOQ 40 mg",             None,     None,    1,  1, "Forme: Carton · Rupture"),
    ("ZERICA M 150 mcg",         Decimal('14'),  Decimal('32200'),   5, 2,  "Forme: Carton · Bas"),
    ("ILACAP",                   Decimal('6'),   Decimal('13800'),   4, 0,  "Forme: Plaquette · Moyen"),
    ("THIOCROS",                 Decimal('6'),   Decimal('13800'),  37, 19, "Forme: Carton · Normal"),
    ("MAIGRIX",                  Decimal('6'),   Decimal('13800'),   2, 2,  "Forme: Carton · Rupture"),
    ("NAVROX",                   Decimal('6'),   Decimal('13800'),  40, 27, "Forme: Carton · Normal"),
    ("LEOPARD",                  None,     None,    6,  0, "Forme: Boîte · Moyen"),
    ("GABEPENTINE 600 mg",       None,     None,    1,  0, "Forme: Plaquette · Bas"),
    ("NAT B",                    Decimal('12'),  Decimal('27600'),  12, 4,  "Forme: Plaquette · Moyen"),
    ("SHARP MAX",                Decimal('20'),  Decimal('46000'),   3, 0,  "Forme: Plaquette · Bas"),
    ("LYNEVIT",                  Decimal('5'),   Decimal('11500'),   4, 0,  "Forme: Plaquette · Moyen"),
    ("ETHOMEX",                  Decimal('7'),   Decimal('16100'),   2, 0,  "Forme: Plaquette · Bas"),
    ("EXACTIVE",                 None,     None,    2,  0, "Forme: Boîte · Bas"),
    ("BAUME",                    Decimal('2'),   Decimal('4600'),   18, 12, "Forme: Boîte · Moyen"),
    ("ORTHOGLIC",                Decimal('7'),   Decimal('16100'),  40, 23, "Normal"),
    ("CORT 80",                  None,     None,    0,  0, "Forme: Carton · Rupture"),
    ("Carnorex",                 None,     None,    5,  2, "Forme: Carton · Bas"),
]


class Command(BaseCommand):
    help = "Charge le stock officiel de la pharmacie CRF-MK (25 produits)."

    def handle(self, *args, **options):
        rate = get_current_rate()
        admin = User.objects.filter(is_staff=True).first()
        crees, existants = 0, 0

        for nom, prix_usd, prix_fc, quantite, sortie, observation in PRODUITS:
            # Devise manquante → dérivation avec le taux actuel
            if prix_usd is None and prix_fc is not None:
                prix_usd = (prix_fc / rate).quantize(Decimal('0.01'))
            if prix_fc is None and prix_usd is not None:
                prix_fc = (prix_usd * rate).quantize(Decimal('1'))

            obs = observation
            if prix_usd is None:
                obs = (observation + ' · ' if observation else '') + '⚠ Prix à définir'
                prix_usd, prix_fc = Decimal('0'), Decimal('0')

            produit, created = PharmacyProduct.objects.get_or_create(
                name__iexact=nom,
                defaults={
                    'name': nom,
                    'price_usd': prix_usd,
                    'price_fc': prix_fc,
                    'observation': obs,
                },
            )
            if not created:
                existants += 1
                continue

            crees += 1
            self.stdout.write(f"  + {nom} — {prix_usd}$ / {prix_fc} FC (stock restant: {quantite - sortie})")

            # Historique tracé : entrée du stock initial + sortie "déjà utilisé"
            if quantite > 0:
                StockMovement.objects.create(
                    product=produit, movement_type=StockMovement.Type.IN,
                    quantity=quantite, reason="Stock initial (seed CRF-MK)", created_by=admin)
            if sortie > 0:
                StockMovement.objects.create(
                    product=produit, movement_type=StockMovement.Type.OUT,
                    quantity=sortie, reason="Historique — déjà utilisé (seed CRF-MK)", created_by=admin)

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé : {crees} produits créés, {existants} déjà existants (ignorés). "
            f"Taux FC de référence : {rate}."
        ))