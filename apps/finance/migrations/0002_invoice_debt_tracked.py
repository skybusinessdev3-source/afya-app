from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='invoice',
            name='debt_tracked',
            field=models.BooleanField(blank=True, default=None, null=True,
                                      verbose_name='Créance stockée'),
        ),
    ]
