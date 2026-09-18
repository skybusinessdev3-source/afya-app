"""
Suppression de patients (et de TOUTES leurs données liées).

Usage :
    python manage.py supprimer_patients              # tous les patients (confirmation demandée)
    python manage.py supprimer_patients --id 12      # un seul patient
    python manage.py supprimer_patients --yes        # sans confirmation (pour script)

⚠️  IRRÉVERSIBLE — faire une sauvegarde de la base AVANT :
    sudo -u postgres pg_dump afya_db > /root/backup_avant_reset.sql

Sont supprimés : patients, leurs factures, paiements, séances, examens labo,
actes de médecine, soins à domicile, rendez-vous et dettes.
Sont CONSERVÉS : les ventes de pharmacie (le lien patient est simplement retiré),
les dépenses, les utilisateurs, les produits et le journal d'activité.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.appointments.models import Appointment
from apps.audit.models import AuditLog
from apps.audit.utils import log_event
from apps.centre.models import Session
from apps.finance.models import Debt, Invoice, Payment
from apps.home_care.models import HomeCareService
from apps.laboratory.models import LaboratoryRecord
from apps.medicine.models import MedicineRecord
from apps.patients.models import Patient


class Command(BaseCommand):
    help = "Supprime tous les patients (ou un seul avec --id) et leurs données liées."

    def add_arguments(self, parser):
        parser.add_argument('--id', type=int, default=None,
                            help="Supprimer uniquement le patient avec cet ID.")
        parser.add_argument('--yes', action='store_true',
                            help="Ne pas demander de confirmation.")

    def handle(self, *args, **options):
        if options['id']:
            qs = Patient.objects.filter(pk=options['id'])
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"Patient #{options['id']} introuvable."))
                return
            cible = f"le patient « {qs.first().full_name} »"
        else:
            qs = Patient.objects.all()
            cible = "TOUS les patients"

        total = qs.count()
        if total == 0:
            self.stdout.write("Aucun patient à supprimer.")
            return

        # --- Aperçu de ce qui sera supprimé ---
        patient_ids = list(qs.values_list('id', flat=True))
        invoices = Invoice.objects.filter(patient_id__in=patient_ids)
        apercu = [
            ('Patients', total),
            ('Factures', invoices.count()),
            ('Paiements', Payment.objects.filter(invoice__in=invoices).count()),
            ('Séances (centre)', Session.objects.filter(patient_id__in=patient_ids).count()),
            ('Examens (labo)', LaboratoryRecord.objects.filter(patient_id__in=patient_ids).count()),
            ('Actes (médecine)', MedicineRecord.objects.filter(patient_id__in=patient_ids).count()),
            ('Soins à domicile', HomeCareService.objects.filter(patient_id__in=patient_ids).count()),
            ('Rendez-vous', Appointment.objects.filter(patient_id__in=patient_ids).count()),
            ('Dettes', Debt.objects.filter(patient_id__in=patient_ids).count()),
        ]
        self.stdout.write(self.style.WARNING(f"\n⚠️  Vous allez supprimer {cible} :"))
        for label, n in apercu:
            self.stdout.write(f"   • {label:.<32} {n}")
        self.stdout.write("   (Ventes de pharmacie, dépenses, produits et utilisateurs : CONSERVÉS.)\n")

        # --- Confirmation ---
        if not options['yes']:
            reponse = input("Tapez SUPPRIMER pour confirmer : ").strip()
            if reponse != 'SUPPRIMER':
                self.stdout.write("Annulé — rien n'a été supprimé.")
                return

        # --- Suppression (ordre imposé par les contraintes PROTECT) ---
        with transaction.atomic():
            Payment.objects.filter(invoice__in=invoices).delete()        # 1) paiements d'abord
            LaboratoryRecord.objects.filter(patient_id__in=patient_ids).delete()
            MedicineRecord.objects.filter(patient_id__in=patient_ids).delete()
            HomeCareService.objects.filter(patient_id__in=patient_ids).delete()
            invoices.delete()                                            # 2) factures ensuite
            qs.delete()                                                  # 3) patients enfin
            #    (CASCADE automatique : séances, rendez-vous, dettes —
            #     SET_NULL automatique : ventes de pharmacie conservées)

            log_event(user=None, action=AuditLog.Actions.DELETE, module='patients',
                      new_value={'commande': 'supprimer_patients',
                                 'patients_supprimes': total,
                                 'id': options['id']})

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ {total} patient(s) supprimé(s) avec toutes leurs données liées."))