from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laboratory', '0002_laboratoryrecord_prescriber_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='laboratoryrecord',
            name='prescriber_paid',
            field=models.BooleanField(default=False, verbose_name='Part prescripteur déjà versée'),
        ),
        migrations.AddField(
            model_name='laboratoryrecord',
            name='prescriber_paid_on',
            field=models.DateField(blank=True, null=True, verbose_name='Part versée le'),
        ),
    ]
