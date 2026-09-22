"""
Réinitialisation des données AFYA — remise à zéro de l'activité.

EFFACE : patients, séances, factures, paiements, dépenses, dettes, ventes
         pharmacie, mouvements de stock, examens labo (actes), soins
         infirmiers, soins à domicile, rendez-vous, notifications, audit.

GARDE  : utilisateurs, messagerie, produits pharmacie (stock inclus),
         catalogue des examens, entreprises, personnel, configuration.

Usage : python manage.py reinitialiser_donnees --settings=config.settings.production
"""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Efface toute l'activité (patients, finances, actes…) en gardant la configuration."

    def handle(self, *args, **options):
        from apps.appointments.models import Appointment
        from apps.audit.models import AuditLog
        from apps.audit.utils import log_event
        from apps.centre.models import Session
        from apps.finance.models import Debt, Expense, Invoice, Payment
        from apps.home_care.models import HomeCarePaymentSplit, HomeCareService
        from apps.laboratory.models import LaboratoryRecord
        from apps.medicine.models import MedicineRecord
        from apps.notifications.models import Notification
        from apps.patients.models import Patient
        from apps.pharmacy.models import PharmacySale, StockMovement

        # Ordre : les enfants avant les parents (clés étrangères)
        cibles = [
            ('Paiements',                 Payment),
            ('Dettes',                    Debt),
            ('Répartitions domicile',     HomeCarePaymentSplit),
            ('Mouvements de stock',       StockMovement),
            ('Ventes pharmacie',          PharmacySale),
            ('Séances du centre',         Session),
            ('Examens labo (actes)',      LaboratoryRecord),
            ('Soins infirmiers',          MedicineRecord),
            ('Soins à domicile',          HomeCareService),
            ('Rendez-vous',               Appointment),
            ('Factures',                  Invoice),
            ('Dépenses',                  Expense),
            ('Patients',                  Patient),
            ('Notifications',             Notification),
            ("Journal d'audit",           AuditLog),
        ]

        self.stdout.write(self.style.WARNING('\n=== RÉINITIALISATION DES DONNÉES ==='))
        self.stdout.write('Les éléments suivants vont être DÉFINITIVEMENT effacés :')
        total = 0
        for label, model in cibles:
            n = model.objects.count()
            total += n
            self.stdout.write(f'  - {label:28s}: {n}')
        self.stdout.write(self.style.WARNING(f'  TOTAL : {total} enregistrements'))
        self.stdout.write('\nSeront conservés : utilisateurs, messagerie, produits'
                          ' pharmacie, catalogue examens, entreprises, personnel, configuration.')

        reponse = input('\nPour confirmer, tape exactement : EFFACER\n> ')
        if reponse.strip() != 'EFFACER':
            self.stdout.write(self.style.ERROR('Annulé — rien n\'a été effacé.'))
            return

        with transaction.atomic():
            details = []
            for label, model in cibles:
                n = model.objects.count()
                if n:
                    model.objects.all().delete()
                details.append(f'{label}: {n}')

        self.stdout.write(self.style.SUCCESS('\n✔ Réinitialisation terminée.'))
        for d in details:
            self.stdout.write(f'  {d}')

        # Trace dans le journal d'audit (fraîchement vidé)
        try:
            log_event(user=None, action='DELETE', module='system',
                      old_value='Réinitialisation complète des données — ' + ' | '.join(details))
        except Exception:
            pass
