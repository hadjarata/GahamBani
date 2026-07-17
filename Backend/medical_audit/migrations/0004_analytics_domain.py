from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('medical_audit', '0003_notifications_domain')]

    operations = [
        migrations.AlterField(
            model_name='medicalauditevent',
            name='domain',
            field=models.CharField(
                choices=[
                    ('MONITORING', 'Monitoring'),
                    ('MEDICAL_RECORDS', 'Medical records'),
                    ('ALERTS', 'Alerts'),
                    ('NOTIFICATIONS', 'Notifications'),
                    ('ANALYTICS', 'Analytics'),
                ],
                max_length=30,
            ),
        ),
    ]
