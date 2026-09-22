from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0005_company_facturation_entreprise'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrescriberConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.CharField(choices=[('GENERAL_CONSULTATION', 'Médecine générale — Consultation'), ('GENERAL_OTHER', 'Médecine générale — Autre prestation'), ('MANUAL', 'Médecine manuelle'), ('MANUAL_OTHER', 'Médecine manuelle — Autre prestation')], max_length=30)),
                ('tariff_usd', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Tarif de base ($)')),
                ('prescriber_pct', models.DecimalField(decimal_places=2, max_digits=5, verbose_name='% médecin')),
                ('is_active', models.BooleanField(default=True)),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prescriber_configs', to='settings_app.staff')),
            ],
            options={
                'ordering': ['staff__last_name', 'category'],
                'unique_together': {('staff', 'category')},
            },
        ),
    ]
