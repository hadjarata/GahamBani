import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
from django.utils import timezone


def prepare_legacy_alerts(apps, schema_editor):
    alert = apps.get_model('alerts', 'MedicalAlert')
    unsupported = alert.objects.exclude(status='NEW')
    if unsupported.exists():
        raise RuntimeError(
            'Legacy transitioned alerts require manual actor/date review before this migration.',
        )
    alert.objects.filter(status='NEW').update(status='OPEN')
    alert.objects.filter(niveau='WARNING').update(niveau='HIGH')
    for item in alert.objects.all().iterator():
        item.rule_code = f'LEGACY_{item.type}'
        item.rule_name = 'Legacy alert'
        item.source_type = 'alerts.legacy'
        item.detected_at = item.created_at
        item.metadata = {'legacy_source': item.source}
        item.save(update_fields=('rule_code', 'rule_name', 'source_type', 'detected_at', 'metadata'))


class Migration(migrations.Migration):
    dependencies = [
        ('alerts', '0002_remove_medicalalert_is_read_medicalalert_status_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveIndex(model_name='medicalalert', name='alerts_medi_patient_2ec256_idx'),
        migrations.AddField(model_name='medicalalert', name='acknowledged_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='medicalalert', name='detected_at', field=models.DateTimeField(default=timezone.now)),
        migrations.AddField(model_name='medicalalert', name='dismissed_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='medicalalert', name='handled_by', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handled_medical_alerts', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='medicalalert', name='metadata', field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name='medicalalert', name='observed_value', field=models.CharField(blank=True, max_length=100)),
        migrations.AddField(model_name='medicalalert', name='resolved_at', field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='medicalalert', name='rule_code', field=models.CharField(default='LEGACY', max_length=100)),
        migrations.AddField(model_name='medicalalert', name='rule_name', field=models.CharField(default='Legacy alert', max_length=255)),
        migrations.AddField(model_name='medicalalert', name='source_id', field=models.UUIDField(blank=True, null=True)),
        migrations.AddField(model_name='medicalalert', name='source_type', field=models.CharField(default='alerts.legacy', max_length=100)),
        migrations.AddField(model_name='medicalalert', name='status_reason', field=models.TextField(blank=True)),
        migrations.AddField(model_name='medicalalert', name='unit', field=models.CharField(blank=True, max_length=30)),
        migrations.AlterField(model_name='medicalalert', name='patient', field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='medical_alerts', to='profiles.patientprofile', verbose_name='patient profile')),
        migrations.RunPython(prepare_legacy_alerts, migrations.RunPython.noop),
        migrations.AlterField(model_name='medicalalert', name='niveau', field=models.CharField(choices=[('INFO', 'Info'), ('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High'), ('CRITICAL', 'Critical')], default='INFO', max_length=10)),
        migrations.AlterField(model_name='medicalalert', name='status', field=models.CharField(choices=[('OPEN', 'Open'), ('ACKNOWLEDGED', 'Acknowledged'), ('RESOLVED', 'Resolved'), ('DISMISSED', 'Dismissed')], default='OPEN', max_length=15)),
        migrations.AlterField(model_name='medicalalert', name='type', field=models.CharField(choices=[('HYPERTENSION', 'Blood pressure'), ('DIABETES', 'Blood glucose'), ('HEART_RATE', 'Heart rate'), ('GENERAL', 'General')], default='GENERAL', max_length=20, verbose_name='type')),
        migrations.AlterField(model_name='medicalalert', name='rule_code', field=models.CharField(max_length=100)),
        migrations.AlterField(model_name='medicalalert', name='rule_name', field=models.CharField(max_length=255)),
        migrations.AlterField(model_name='medicalalert', name='source_type', field=models.CharField(max_length=100)),
        migrations.AlterModelOptions(name='medicalalert', options={'ordering': ('-detected_at', '-created_at')}),
        migrations.AddIndex(model_name='medicalalert', index=models.Index(fields=['patient', 'status', '-detected_at'], name='alert_patient_status_idx')),
        migrations.AddIndex(model_name='medicalalert', index=models.Index(fields=['rule_code', '-detected_at'], name='alert_rule_date_idx')),
        migrations.AddIndex(model_name='medicalalert', index=models.Index(fields=['source_type', 'source_id'], name='alert_source_idx')),
        migrations.AddIndex(model_name='medicalalert', index=models.Index(fields=['niveau', '-detected_at'], name='alert_level_date_idx')),
        migrations.AddConstraint(model_name='medicalalert', constraint=models.UniqueConstraint(condition=Q(source_id__isnull=False), fields=('source_type', 'source_id', 'rule_code'), name='unique_alert_source_rule')),
        migrations.AddConstraint(model_name='medicalalert', constraint=models.CheckConstraint(condition=(Q(status='OPEN', acknowledged_at__isnull=True, resolved_at__isnull=True, dismissed_at__isnull=True) | Q(status='ACKNOWLEDGED', acknowledged_at__isnull=False, resolved_at__isnull=True, dismissed_at__isnull=True, handled_by__isnull=False) | Q(status='RESOLVED', acknowledged_at__isnull=False, resolved_at__isnull=False, dismissed_at__isnull=True, handled_by__isnull=False) | Q(status='DISMISSED', resolved_at__isnull=True, dismissed_at__isnull=False, handled_by__isnull=False)), name='alert_status_dates_consistent')),
    ]
