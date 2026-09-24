from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('medicine', '0003_medicinerecord_prescriber'),
    ]

    operations = [
        migrations.AddField(
            model_name='medicinerecord',
            name='prescriber_paid',
            field=models.BooleanField(default=False, verbose_name='Part prescripteur déjà versée'),
        ),
        migrations.AddField(
            model_name='medicinerecord',
            name='prescriber_paid_on',
            field=models.DateField(blank=True, null=True, verbose_name='Part versée le'),
        ),
    ]
