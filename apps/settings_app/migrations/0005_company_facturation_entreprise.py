from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('settings_app', '0004_alter_medicinesplitconfig_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='facturation_entreprise',
            field=models.BooleanField(
                default=False,
                verbose_name="Facturé à l'entreprise (créances)"),
        ),
    ]
