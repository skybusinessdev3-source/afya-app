from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0006_prescriberconfig'),
    ]

    operations = [
        migrations.AddField(
            model_name='homecaresplitconfig',
            name='consult_doctor_pct',
            field=models.DecimalField(decimal_places=2, default=50, max_digits=5, verbose_name='% médecin (consultation)'),
        ),
        migrations.AddField(
            model_name='homecaresplitconfig',
            name='consult_center_pct',
            field=models.DecimalField(decimal_places=2, default=50, max_digits=5, verbose_name='% centre (consultation)'),
        ),
    ]
