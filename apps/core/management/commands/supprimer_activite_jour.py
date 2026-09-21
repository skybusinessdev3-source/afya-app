"""
Supprime l'activité d'UN patient sur UNE journée précise (erreur de saisie).

Usage :
    python manage.py supprimer_activite_jour --patient "kibanga" --date 2026-09-14
    python manage.py supprimer_activite_jour --patient "kibanga" --date 2026-09-14 --yes
    python manage.py supprimer_activite_jour --patient "kibanga" --date 2026-09-14 --avec-patient

Sont supprimés pour ce patient CE JOUR-LÀ uniquement :
séances, examens labo, actes médecine, soins à domicile, ventes pharmacie
(stock restauré), factures et paiements du jour.
Le DOSSIER patient est conservé (sauf --avec-patient).
La suppression est tracée dans le journal d'activité.

⚠️  IRRÉVERSIBLE — en cas de doute, sauvegarde d'abord :
    sudo -u postgres pg_dump afya_db > /root/backup_avant_suppression.sql
"""

from datetime import date as date_cls

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.appointments.models import Appointment
from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.centre.models import Session
from apps.finance.models import Invoice, Payment
from apps.home_care.models import HomeCareService
from apps.laboratory.models import LaboratoryRecord
from apps.medicine.models import MedicineRecord
from apps.patients.models import Patient
from apps.pharmacy.models import PharmacySale, StockMovement


class Command(BaseCommand):
    help = "Supprime l'activité d'un patient sur une journée précise (dossier conservé)."

    def add_arguments(self, parser):
        parser.add_argument('--patient', required=True,
                            help="Nom (ou partie du nom) du patient. Ex : \"kibanga\"")
        parser.add_argument('--date', required=True,
                            help="Jour concerné (AAAA-MM-JJ). Ex : 2026-09-14")
        parser.add_argument('--avec-patient', action='store_true',
                            help="Supprimer AUSSI le dossier patient (s'il ne doit pas exister du tout).")
        parser.add_argument('--yes', action='store_true',
                            help="Ne pas demander de confirmation.")

    def handle(self, *args, **options):
        terme = options['patient'].strip()
        try:
            d = date_cls.fromisoformat(options['date'])
        except ValueError:
            self.stderr.write(self.style.ERROR("Date invalide — format attendu : AAAA-MM-JJ."))
            return

        patients = Patient.objects.filter(
            Q(last_name__icontains=terme) |
            Q(middle_name__icontains=terme) |
            Q(first_name__icontains=terme))
        if not patients.exists():
            self.stderr.write(self.style.ERROR(f"Aucun patient ne correspond à « {terme} »."))
            return
        if patients.count() > 1:
            self.stderr.write(self.style.ERROR("Plusieurs patients correspondent — précise le nom :"))
            for p in patients:
                self.stderr.write(f"   #{p.id} — {p.full_name}")
            return
        patient = patients.first()

        # --- Tout ce qui sera supprimé ce jour-là ---
        sessions = Session.objects.filter(patient=patient, date=d)
        lab = LaboratoryRecord.objects.filter(patient=patient, date=d)
        med = MedicineRecord.objects.filter(patient=patient, date=d)
        home = HomeCareService.objects.filter(patient=patient, date=d)
        ventes = PharmacySale.objects.filter(patient=patient, date=d)
        factures = Invoice.objects.filter(patient=patient, date=d)
        paiements = Payment.objects.filter(invoice__in=factures)
        rdv = Appointment.objects.filter(patient=patient, date=d)

        apercu = [
            ('Séances (centre)', sessions.count()),
            ('Examens (labo)', lab.count()),
            ('Actes (médecine)', med.count()),
            ('Soins à domicile', home.count()),
            ('Ventes pharmacie (stock restauré)', ventes.count()),
            ('Factures', factures.count()),
            ('Paiements', paiements.count()),
            ('Rendez-vous', rdv.count()),
        ]
        if not any(n for _, n in apercu) and not options['avec_patient']:
            self.stdout.write(f"Aucune activité trouvée pour {patient.full_name} le {d:%d/%m/%Y}.")
            return

        self.stdout.write(self.style.WARNING(
            f"\n⚠️  Suppression pour « {patient.full_name} » le {d:%d/%m/%Y} :"))
        for label, n in apercu:
            self.stdout.write(f"   • {label:.<38} {n}")
        if options['avec_patient']:
            self.stdout.write("   • DOSSIER PATIENT................. SUPPRIMÉ AUSSI")
        else:
            self.stdout.write("   (Le dossier patient est CONSERVÉ — seule la journée est effacée.)\n")

        if not options['yes']:
            if input("Tapez SUPPRIMER pour confirmer : ").strip() != 'SUPPRIMER':
                self.stdout.write("Annulé — rien n'a été supprimé.")
                return

        with transaction.atomic():
            paiements.delete()                                    # 1) paiements (PROTECT)
            lab.delete(); med.delete(); home.delete()             # 2) actes du jour
            StockMovement.objects.filter(sale__in=ventes).delete()  # 3) stock restauré
            ventes.delete()
            factures.delete()                                     # 4) factures du jour
            sessions.delete(); rdv.delete()                       # 5) séances + RDV
            if options['avec_patient']:
                patient.delete()                                  # 6) dossier (optionnel)

            log_event(user=None, action=AuditLog.Actions.DELETE, module='patients',
                      new_value={'commande': 'supprimer_activite_jour',
                                 'patient': patient.full_name, 'date': str(d),
                                 'dossier_supprime': bool(options['avec_patient'])})

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Activité du {d:%d/%m/%Y} supprimée pour « {patient.full_name} »"
            + (" — dossier patient supprimé aussi." if options['avec_patient']
               else " — dossier patient conservé.")))