from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home_care', '0003_homecareservice_consultation_et_part_medecin'),
    ]

    operations = [
        migrations.AddField(
            model_name='homecareservice',
            name='sessions_paid',
            field=models.PositiveIntegerField(default=0, verbose_name='Séances payées'),
        ),
    ]
