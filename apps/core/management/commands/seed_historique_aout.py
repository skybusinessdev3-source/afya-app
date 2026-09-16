from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.pharmacy.models import PharmacyProduct, StockMovement
from apps.settings_app.models import Company, LabExam

# ============================================================
# PATIENTS — récoltés du rapport Excel août 2026
# (nom complet, entité, séances prescrites, séances effectuées)
# Entités : LTJ / GGA / ADVANS → entreprises ; '' = privé
# ============================================================
PATIENTS = [
    # --- LTJ (prise en charge) ---
    ("Dileka Nsimba Jérémie", "LTJ", 24, 4),
    ("Patrick Kotene", "LTJ", 24, 9),
    ("Isabelle Kombe", "LTJ", 12, 3),
    ("Kalala Ntumba Stany", "LTJ", 13, 6),
    # --- GGA puis privé ---
    ("Guillaume Mwamba", "GGA", 10, 10),
    # --- ADVANS ---
    ("Betty Kinenga", "ADVANS", 10, 10),
    # --- Privés / Famille (du journal détaillé) ---
    ("Mukeza Geneviève", "", 0, 0),
    ("Omiazila Valentin", "", 0, 0),
    ("Lukombo Jean", "", 0, 0),
    ("Aline Ondongo", "", 0, 0),
    ("Jean-Marie Mongila", "", 0, 0),
    ("Dieudonné Ngongo", "", 0, 0),
    ("Marcelline Kuta", "", 0, 0),
    ("Miel Kambeya", "", 0, 0),
    ("Fuge Julienne", "", 0, 0),
    ("Marie-Opportune Masika", "", 0, 0),
    ("Yvette Mbolo", "", 0, 0),
    ("Moïse Kabongo", "", 0, 0),
    ("Rebecca Mudikongo", "", 0, 0),
    ("Monique Musuamba", "", 0, 0),
    ("Karen Kibanga", "", 0, 0),
    ("Hattie Kashoba", "", 0, 0),
    ("Gisèle Kabombo", "", 0, 0),
    ("Masiala Adeline", "", 0, 0),
    ("Loola Towa Dophine", "", 0, 0),
    ("Fernande Damawo", "", 0, 0),
    ("Stéphanie Mabungu", "", 0, 0),
    ("Eldad Jarold Miracle", "", 0, 0),
    ("Sylvie Mutiaka", "", 0, 0),
    ("Souzy-Presnelle Makuiza", "", 0, 0),
    ("Régine Ombokana", "", 0, 0),
    ("Roy Matele", "", 0, 0),
    ("Charlotte Kanda", "", 0, 0),
    ("Sylvie Owanga", "", 0, 0),
    ("Lukwene Jonas", "", 0, 0),
    ("Fabruce", "", 0, 0),
    ("Ntumba Bukasa", "", 0, 0),
    ("Alain Kashoba", "", 0, 0),
    ("Marcelinne Yagene", "", 0, 0),
]

# ============================================================
# PRODUITS — inventaire de fin août 2026 (feuille Liste_des_produits)
# (nom complet, prix_usd, prix_fc, quantité initiale, déjà utilisé, reste attendu)
# Le script AJUSTE le stock actuel au "reste" via un mouvement
# correctif tracé (§11 : jamais de modification silencieuse)
# ============================================================
PRODUITS = [
    ("CARBONEX", Decimal('0'), Decimal('0'), 5, 0, 5),
    ("DESPAIN 25 mg", Decimal('0'), Decimal('0'), 12, 0, 12),
    ("COXOPAIN 30 mg", Decimal('4'), Decimal('9200'), 11, 0, 11),
    ("COXOPAIN 60 mg", Decimal('4'), Decimal('9200'), 5, 0, 5),
    ("COXOPAIN 90 mg", Decimal('5'), Decimal('11500'), 5, 0, 5),
    ("CALLOIDE", Decimal('10'), Decimal('23000'), 12, 8, 4),
    ("FERROTONE", Decimal('0'), Decimal('0'), 8, 0, 8),
    ("NEUROMED 140 mg", Decimal('15'), Decimal('34500'), 2, 1, 1),
    ("PROTOQ 40 mg", Decimal('0'), Decimal('0'), 1, 1, 0),
    ("ZERICA M 150 mcg", Decimal('14'), Decimal('32200'), 5, 0, 5),
    ("ILACAP", Decimal('6'), Decimal('13800'), 2, 0, 2),
    ("THIOCROS", Decimal('6'), Decimal('13800'), 17, 10, 7),
    ("MAIGRIX", Decimal('6'), Decimal('13800'), 2, 2, 0),
    ("NAVROX", Decimal('6'), Decimal('13800'), 21, 19, 2),
    ("LEOPARD", Decimal('0'), Decimal('0'), 6, 0, 6),
    ("GABEPENTINE 600 mg", Decimal('0'), Decimal('0'), 1, 0, 1),
    ("NAT B", Decimal('12'), Decimal('27600'), 12, 4, 8),
    ("SHARP MAX", Decimal('20'), Decimal('46000'), 3, 0, 3),
    ("LYNEVIT", Decimal('5'), Decimal('11500'), 4, 0, 4),
    ("ETHOMEX", Decimal('7'), Decimal('16100'), 2, 0, 2),
    ("EXACTIVE", Decimal('0'), Decimal('0'), 2, 0, 2),
    ("BAUME", Decimal('2'), Decimal('4600'), 18, 7, 11),
    ("ORTHOGLIC", Decimal('7'), Decimal('16100'), 20, 20, 0),
    ("CORT 80", Decimal('0'), Decimal('0'), 0, 0, 0),
    ("Carnorex", Decimal('0'), Decimal('0'), 5, 2, 3),
]

# ============================================================
# EXAMENS MANQUANTS (vérifiés contre la tarification +
# ce rapport : échographies 35$-60$, pack 8 examens 123$)
# ============================================================
EXAMENS_MANQUANTS = [
    ("Échographie", Decimal('40'), Decimal('90000')),        # prix ajustable (35-60 $ observés)
    ("Pack 8 examens", Decimal('123'), Decimal('276750')),   # bilan de Sylvie OWANGA
]


class Command(BaseCommand):
    help = "Charge l'historique août 2026 : patients, ajustement stock, examens manquants."

    def handle(self, *args, **options):
        admin = User.objects.filter(is_staff=True).first()

        # ---------- 1. PATIENTS ----------
        crees, existants = 0, 0
        for nom, entite, prescrit, effectue in PATIENTS:
            company = None
            if entite:
                company, _ = Company.objects.get_or_create(name=entite)
            p, created = Patient.objects.get_or_create(
                last_name=nom,
                defaults={
                    'first_name': '',
                    'sex': 'M',
                    'company': company,
                    'sessions_prescribed': prescrit,
                },
            )
            if created:
                crees += 1
                self.stdout.write(f"  + patient : {nom}" + (f" ({entite})" if entite else ""))
            else:
                existants += 1
                # Met à jour les infos si plus complètes
                changed = False
                if company and p.company_id != company.id:
                    p.company = company
                    changed = True
                if prescrit > p.sessions_prescribed:
                    p.sessions_prescribed = prescrit
                    changed = True
                if changed:
                    p.save()

        # ---------- 2. PRODUITS (ajustement au stock de fin août) ----------
        stock_ok, stock_ajuste, crees_p = 0, 0, 0
        for nom, usd, fc, qte, sortie, reste in PRODUITS:
            produit = PharmacyProduct.objects.filter(name__iexact=nom).first()
            if produit is None:
                # Création complète si absent du catalogue
                obs = '' if usd > 0 else '⚠ Prix à définir'
                produit = PharmacyProduct.objects.create(name=nom, price_usd=usd, price_fc=fc,
                                                         observation=obs)
                if qte > 0:
                    StockMovement.objects.create(product=produit, movement_type=StockMovement.Type.IN,
                                                 quantity=qte, reason="Stock initial (historique août)",
                                                 created_by=admin)
                if sortie > 0:
                    StockMovement.objects.create(product=produit, movement_type=StockMovement.Type.OUT,
                                                 quantity=sortie, reason="Historique — utilisé (août)",
                                                 created_by=admin)
                crees_p += 1
                self.stdout.write(f"  + produit : {nom} (stock: {produit.stock_available})")
                continue

            # Prix : mise à jour si le produit n'en avait pas
            if produit.price_usd == 0 and usd > 0:
                produit.price_usd, produit.price_fc = usd, fc
                produit.save(update_fields=['price_usd', 'price_fc'])

            # Ajustement du stock au "reste" du fichier (mouvement correctif tracé)
            ecart = reste - produit.stock_available
            if ecart != 0:
                StockMovement.objects.create(
                    product=produit,
                    movement_type=StockMovement.Type.IN if ecart > 0 else StockMovement.Type.OUT,
                    quantity=abs(ecart),
                    reason="Ajustement inventaire fin août 2026",
                    created_by=admin,
                )
                stock_ajuste += 1
                self.stdout.write(f"  ~ stock {nom} : {produit.stock_available} -> {reste}")
            else:
                stock_ok += 1

        # ---------- 3. EXAMENS MANQUANTS ----------
        crees_e = 0
        for nom, usd, fc in EXAMENS_MANQUANTS:
            _, created = LabExam.objects.get_or_create(
                name=nom, defaults={'price_usd': usd, 'price_fc': fc})
            if created:
                crees_e += 1
                self.stdout.write(f"  + examen : {nom} ({usd}$)")

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé : {crees} patients créés ({existants} déjà connus), "
            f"{crees_p} produits créés / {stock_ajuste} stocks ajustés / {stock_ok} déjà conformes, "
            f"{crees_e} examens ajoutés."
        ))