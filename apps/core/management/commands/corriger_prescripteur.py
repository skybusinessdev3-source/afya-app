"""
Ajoute/corrige le prescripteur sur des examens de labo déjà enregistrés.

Usage :
    python manage.py corriger_prescripteur --patient "omiazila" --prescripteur "Dr. Mulamba"
    python manage.py corriger_prescripteur --patient "omiazila" --date 2026-09-14 --prescripteur "Dr. Mulamba"
    python manage.py corriger_prescripteur --patient "omiazila" --prescripteur "Dr. X" --forcer
    python manage.py corriger_prescripteur --patient "omiazila" --prescripteur "Dr. X" --yes

- Seuls les examens SANS prescripteur sont corrigés (sauf --forcer).
- Les montants (part prescripteur 20%, équipe, centre) ne changent PAS :
  ils sont figés à la création et déjà corrects — on ajoute juste le nom.
- La correction est tracée dans le journal d'activité.
"""

from datetime import date as date_cls

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.laboratory.models import LaboratoryRecord
from apps.patients.models import Patient


class Command(BaseCommand):
    help = "Ajoute le prescripteur sur des examens labo existants (montants inchangés)."

    def add_arguments(self, parser):
        parser.add_argument('--patient', required=True,
                            help="Nom (ou partie du nom) du patient. Ex : \"omiazila\"")
        parser.add_argument('--prescripteur', required=True,
                            help="Nom du prescripteur à enregistrer. Ex : \"Dr. Mulamba\"")
        parser.add_argument('--date', default=None,
                            help="Limiter à un jour précis (AAAA-MM-JJ).")
        parser.add_argument('--forcer', action='store_true',
                            help="Remplacer même les examens qui ont déjà un prescripteur.")
        parser.add_argument('--yes', action='store_true',
                            help="Ne pas demander de confirmation.")

    def handle(self, *args, **options):
        terme = options['patient'].strip()
        prescripteur = options['prescripteur'].strip()
        if not prescripteur:
            self.stderr.write(self.style.ERROR("Le nom du prescripteur ne peut pas être vide."))
            return

        # --- Patients correspondants ---
        patients = Patient.objects.filter(
            Q(last_name__icontains=terme) |
            Q(middle_name__icontains=terme) |
            Q(first_name__icontains=terme))
        if not patients.exists():
            self.stderr.write(self.style.ERROR(f"Aucun patient ne correspond à « {terme} »."))
            return

        # --- Examens concernés ---
        records = LaboratoryRecord.objects.filter(patient__in=patients)
        if options['date']:
            try:
                d = date_cls.fromisoformat(options['date'])
            except ValueError:
                self.stderr.write(self.style.ERROR("Date invalide — format attendu : AAAA-MM-JJ."))
                return
            records = records.filter(date=d)
        if not options['forcer']:
            records = records.filter(prescriber_name='')

        total = records.count()
        if total == 0:
            self.stdout.write("Aucun examen à corriger (déjà un prescripteur, ou aucun examen trouvé).")
            return

        # --- Aperçu ---
        self.stdout.write(self.style.WARNING(
            f"\n⚠️  Prescripteur « {prescripteur} » sera ajouté sur {total} examen(s) :"))
        for p in patients:
            self.stdout.write(f"   Patient : {p.full_name}")
        for r in records.select_related('exam')[:20]:
            self.stdout.write(f"       - {r.date:%d/%m/%Y} : {r.exam.name} "
                              f"({r.amount_original} {r.currency_original})")
        if total > 20:
            self.stdout.write(f"       ... et {total - 20} autre(s)")
        self.stdout.write("   (Les montants et la répartition NE changent PAS.)\n")

        if not options['yes']:
            if input("Tapez CORRIGER pour confirmer : ").strip() != 'CORRIGER':
                self.stdout.write("Annulé — rien n'a été modifié.")
                return

        nb = records.update(prescriber_name=prescripteur)
        log_event(user=None, action=AuditLog.Actions.UPDATE, module='laboratory',
                  new_value={'commande': 'corriger_prescripteur',
                             'patient': terme, 'prescripteur': prescripteur,
                             'examens_corriges': nb})

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {nb} examen(s) corrigé(s) — prescripteur « {prescripteur} » enregistré."))