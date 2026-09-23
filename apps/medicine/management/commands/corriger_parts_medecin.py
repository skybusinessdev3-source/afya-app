"""
Recalcule les parts prescripteur/centre des prestations de médecine
selon la CONFIGURATION INDIVIDUELLE du médecin (PrescriberConfig).

Usage (SIMULATION par défaut — rien n'est modifié) :
    python manage.py corriger_parts_medecin --medecin "Mutamba"

Pour appliquer réellement :
    python manage.py corriger_parts_medecin --medecin "Mutamba" --appliquer
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import models

from apps.medicine.models import MedicineRecord
from apps.settings_app.models import PrescriberConfig, Staff


class Command(BaseCommand):
    help = "Corrige les parts médecin/centre selon la config individuelle (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument('--medecin', required=True,
                            help="Nom ou partie du nom du médecin (ex: Mutamba)")
        parser.add_argument('--appliquer', action='store_true',
                            help="Applique réellement les corrections")

    def handle(self, *args, **opts):
        nom = opts['medecin'].strip()
        appliquer = opts['appliquer']

        # 1) Retrouver le médecin dans Staff
        candidats = [s for s in Staff.objects.all()
                     if nom.lower() in f"{s.first_name} {s.last_name}".lower()
                     or nom.lower() in str(s).lower()]
        if not candidats:
            self.stdout.write(self.style.ERROR(f"Aucun membre du personnel ne contient « {nom} »."))
            return
        staff = candidats[0]
        self.stdout.write(f"Médecin trouvé : {staff} (id={staff.id})")

        configs = PrescriberConfig.objects.filter(staff=staff, is_active=True)
        if not configs:
            self.stdout.write(self.style.ERROR("Aucune configuration active pour ce médecin."))
            return

        total_changes = 0
        for cfg in configs:
            part_voulue = (cfg.tariff_usd * cfg.prescriber_pct / 100).quantize(Decimal('0.01'))
            self.stdout.write(
                f"\n== {cfg.get_category_display()} : tarif {cfg.tariff_usd}$ × {cfg.prescriber_pct}% "
                f"= {part_voulue}$ (plafonné au montant facturé) ==")

            # Prestations liées par le FK OU par le nom libre (anciennes saisies)
            records = (MedicineRecord.objects
                       .filter(category=cfg.category)
                       .filter(models.Q(prescriber=staff)
                               | models.Q(prescriber_name__icontains=staff.last_name)
                               | models.Q(prescriber_name__icontains=staff.first_name))
                       .order_by('date'))
            for r in records:
                part_calc = min(part_voulue, r.amount_usd)
                if r.prescriber_amount_usd == part_calc:
                    continue  # déjà correct
                centre_calc = r.amount_usd - part_calc
                self.stdout.write(
                    f"  {r.date:%d/%m/%Y} — {r.patient.full_name} — facturé {r.amount_usd}$ : "
                    f"médecin {r.prescriber_amount_usd}$ → {part_calc}$ | "
                    f"centre {r.center_amount_usd}$ → {centre_calc}$")
                total_changes += 1
                if appliquer:
                    MedicineRecord.objects.filter(pk=r.pk).update(
                        prescriber_amount_usd=part_calc,
                        center_amount_usd=centre_calc)

        self.stdout.write("")
        if total_changes == 0:
            self.stdout.write(self.style.SUCCESS("Tout est déjà correct, rien à modifier."))
        elif appliquer:
            self.stdout.write(self.style.SUCCESS(f"{total_changes} prestation(s) corrigée(s)."))
        else:
            self.stdout.write(self.style.WARNING(
                f"SIMULATION : {total_changes} prestation(s) seraient corrigées. "
                f"Relance avec --appliquer pour confirmer."))
