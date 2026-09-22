from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('medicine', '0002_medicinerecord_prestation_other_and_more'),
        ('settings_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicinerecord',
            name='prescriber',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medicine_records', to='settings_app.staff', verbose_name='Médecin (Staff)'),
        ),
    ]
