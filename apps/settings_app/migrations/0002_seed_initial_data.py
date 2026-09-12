from decimal import Decimal
from django.utils import timezone
from datetime import datetime

from django.db import migrations


def seed_initial_data(apps, schema_editor):
    """
    Données de démarrage du centre.
    Exécuté une seule fois par environnement — réversible via unseed_initial_data.
    """
    CenterConfig = apps.get_model('settings_app', 'CenterConfig')
    Staff = apps.get_model('settings_app', 'Staff')
    ExchangeRate = apps.get_model('settings_app', 'ExchangeRate')
    LabSplitConfig = apps.get_model('settings_app', 'LabSplitConfig')
    HomeCareSplitConfig = apps.get_model('settings_app', 'HomeCareSplitConfig')
    Service = apps.get_model('centre', 'Service')

    now = timezone.make_aware(datetime(2026, 1, 1))  # effectif rétroactif : valable pour toute l'année

    # 1. Médecin directeur (cf. cahier des charges : Dr. Rémy KAWELE)
    doctor, _ = Staff.objects.get_or_create(
        last_name='KAWELE',
        first_name='Rémy',
        defaults={
            'title': 'DOCTOR',
            'sex': 'M',
            'is_active': True,
        },
    )

    # 2. Configuration du centre
    CenterConfig.objects.get_or_create(
        pk=1,
        defaults={
            'name': 'AFYA - Centre Médical',
            'default_doctor': doctor,
        },
    )

    # 3. Taux de change par défaut : 1 $ = 2 250 FC
    ExchangeRate.objects.get_or_create(
        currency_from='USD',
        currency_to='FC',
        rate=Decimal('2250'),
        effective_from=now,
        defaults={'is_active': True},
    )

    # 4. Répartition laboratoire : 20 % prescripteur ; 60 % équipe / 40 % centre du restant
    LabSplitConfig.objects.get_or_create(
        prescriber_pct=Decimal('20'),
        lab_team_pct=Decimal('60'),
        center_pct=Decimal('40'),
        effective_from=now,
        defaults={'is_active': True},
    )

    # 5. Répartition soins à domicile (⚠️ valeurs par défaut — À AJUSTER selon tes règles réelles)
    HomeCareSplitConfig.objects.get_or_create(
        doctor_pct=Decimal('50'),
        center_pct=Decimal('50'),
        effective_from=now,
        defaults={'is_active': True},
    )

    # 6. Services de base du centre (prix à ajuster)
    services = [
        ('Séance kiné', Decimal('15'), Decimal('33750')),
        ('Consultation', Decimal('20'), Decimal('45000')),
        ('Évaluation', Decimal('25'), Decimal('56250')),
    ]
    for name, price_usd, price_fc in services:
        Service.objects.get_or_create(name=name, defaults={
            'price_usd': price_usd,
            'price_fc': price_fc,
            'is_active': True,
        })


def unseed_initial_data(apps, schema_editor):
    """Retour en arrière propre (utilisé seulement si tu un-apply la migration)."""
    CenterConfig = apps.get_model('settings_app', 'CenterConfig')
    Staff = apps.get_model('settings_app', 'Staff')
    ExchangeRate = apps.get_model('settings_app', 'ExchangeRate')
    LabSplitConfig = apps.get_model('settings_app', 'LabSplitConfig')
    HomeCareSplitConfig = apps.get_model('settings_app', 'HomeCareSplitConfig')
    Service = apps.get_model('centre', 'Service')

    ExchangeRate.objects.all().delete()
    LabSplitConfig.objects.all().delete()
    HomeCareSplitConfig.objects.all().delete()
    Service.objects.filter(name__in=['Séance kiné', 'Consultation', 'Évaluation']).delete()
    CenterConfig.objects.filter(pk=1).delete()
    Staff.objects.filter(last_name='KAWELE', first_name='Rémy').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0001_initial'),  # ← adapte le numéro si différent
        ('centre', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_initial_data, unseed_initial_data),
    ]