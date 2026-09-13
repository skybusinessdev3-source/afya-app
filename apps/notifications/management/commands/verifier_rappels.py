from django.core.management.base import BaseCommand

from apps.notifications.utils import process_due_reminders


class Command(BaseCommand):
    help = "Vérifie les rappels de rendez-vous dus et crée les notifications."

    def handle(self, *args, **options):
        n = process_due_reminders()
        self.stdout.write(self.style.SUCCESS(
            f"Vérification terminée : {n} notification(s) créée(s)."
        ))