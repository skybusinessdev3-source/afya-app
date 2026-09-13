from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.finance.models import get_current_rate
from apps.settings_app.models import LabExam

# Tarification officielle CRF-MK (document « TARIFICATION LABORATOIRE »)
# (nom, prix_usd) — prix_usd = None → prix à définir
EXAMENS = [
    ("NFS (Numération Formule Sanguine)", 10),
    ("VS (Vitesse de sédimentation)", 3),
    ("CRP", 10),
    ("Facteur rhumatoïde (FR)", 23),
    ("Anticorps anti-CCP", 30),
    ("ANA (Anticorps antinucléaires)", None),
    ("HLA-B27 (Spondyloarthrites)", None),
    ("Acide urique", 8),
    ("Calcémie", 40),
    ("Phosphorémie", 13),
    ("Magnésémie", 12),
    ("Vitamine D (25-OH Vitamine D)", 40),
    ("Parathormone (PTH)", 70),
    ("Phosphatases alcalines", 15),
    ("CPK (Créatine phosphokinase)", 30),
    ("LDH", 30),
    ("Aldolase", None),
    ("Vitamine B12", 45),
    ("Folates", None),
    ("TSH", 30),
    ("TP/INR", 30),
    ("TCA", 35),
    ("Glycémie", 3),
    ("Créatinine", 8),
    ("HbA1c", 25),
    ("Bilan lipidique", 66),
    ("Urée", 8),
    ("Ionogramme sanguin", 45),
    ("VIH", 10),
    ("Sérologies selon le contexte (syphilis, HTLV-1, hépatites)", 31),
    ("Électrophorèse des protéines", 40),
    ("Syphilis", 30),
    ("HCV", 25),
    ("Ferritine", 45),
    ("NT-proBNP", 40),
    ("D-Dimer", 40),
    ("HbS", 25),
    ("GE", 3),
    ("Selles", 3),
    ("GB", 3),
    ("HB", 3),
    ("FL", 5),
    ("ALAT", 8.5),
    ("ASAT", 8.5),
    ("Potassium", 20),
    ("PSA Total", 35),
    ("LDL", 30),
    ("Triglycérides", 35),
    ("Sédiment urinaire", 3),
    ("Frottis vaginal à frais", 5),
    ("Frottis vaginal coloré", 10),
    ("Widal", 7),
    ("ECBU", 40),
    ("Coproculture", 40),
    ("ASLO", 25),
    ("Cholestérol total", 30),
    ("HDL", 30),
    ("Bandelette urinaire", 15),
    ("Matériel de prélèvement", 5),
]


class Command(BaseCommand):
    help = "Charge la tarification officielle des examens de laboratoire (CRF-MK)."

    def handle(self, *args, **options):
        rate = get_current_rate()
        crees, existants = 0, 0

        for name, usd in EXAMENS:
            price_usd = Decimal(str(usd)) if usd is not None else Decimal('0')
            price_fc = (price_usd * rate).quantize(Decimal('1')) if usd is not None else Decimal('0')

            defaults = {
                'name': name,
                'price_usd': price_usd,
                'price_fc': price_fc,
                'observation': '' if usd is not None else '⚠ Prix à définir',
            }
            obj, created = LabExam.objects.get_or_create(
                name__iexact=name, defaults=defaults)
            if created:
                crees += 1
                self.stdout.write(f"  + {name} — {price_usd}$ / {price_fc} FC")
            else:
                existants += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé : {crees} examens créés, {existants} déjà existants (ignorés). "
            f"Taux utilisé pour le FC : {rate}."
        ))