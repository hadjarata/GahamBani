from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('medical_audit', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='medicalauditevent', name='domain',
            field=models.CharField(
                choices=[('MONITORING', 'Monitoring'), ('MEDICAL_RECORDS', 'Medical records'), ('ALERTS', 'Alerts')],
                max_length=30,
            ),
        ),
    ]
