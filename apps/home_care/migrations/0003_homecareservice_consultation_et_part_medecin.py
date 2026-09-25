from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('home_care', '0002_remove_homecareservice_amount_original_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='homecareservice',
            name='service_type',
            field=models.CharField(choices=[('SOINS', 'Soins à domicile'), ('CONSULTATION', 'Consultation à domicile')], default='SOINS', max_length=15, verbose_name='Type de prestation'),
        ),
        migrations.AddField(
            model_name='homecareservice',
            name='doctor_paid',
            field=models.BooleanField(default=False, verbose_name='Part médecin déjà versée'),
        ),
        migrations.AddField(
            model_name='homecareservice',
            name='doctor_paid_on',
            field=models.DateField(blank=True, null=True, verbose_name='Part versée le'),
        ),
    ]
