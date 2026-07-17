import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('profiles', '0003_assignment_history_and_integrity'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('recipient_reference', models.UUIDField(editable=False)),
                ('patient_reference', models.UUIDField(blank=True, editable=False, null=True)),
                ('type', models.CharField(choices=[('MEDICAL_ALERT_CREATED', 'Medical alert created'), ('ALERT_ACKNOWLEDGED', 'Alert acknowledged'), ('ALERT_RESOLVED', 'Alert resolved'), ('ALERT_DISMISSED', 'Alert dismissed'), ('SYSTEM', 'System')], max_length=30)),
                ('priority', models.CharField(choices=[('LOW', 'Low'), ('NORMAL', 'Normal'), ('HIGH', 'High'), ('CRITICAL', 'Critical')], default='NORMAL', max_length=10)),
                ('title', models.CharField(max_length=120)),
                ('message', models.CharField(max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('source_domain', models.CharField(max_length=50)),
                ('source_type', models.CharField(max_length=100)),
                ('source_id', models.UUIDField()),
                ('event_code', models.CharField(max_length=100)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('public_metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('patient', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to='profiles.patientprofile')),
                ('recipient', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at', '-id'),
                'indexes': [
                    models.Index(fields=['recipient', 'is_read', '-created_at'], name='notif_rec_read_date_idx'),
                    models.Index(fields=['recipient', '-created_at'], name='notif_rec_date_idx'),
                    models.Index(fields=['type', '-created_at'], name='notif_type_date_idx'),
                    models.Index(fields=['source_type', 'source_id'], name='notif_source_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(fields=('recipient_reference', 'event_code', 'source_type', 'source_id'), name='unique_notification_event_recipient'),
                    models.CheckConstraint(condition=(Q(is_read=False, read_at__isnull=True) | Q(is_read=True, read_at__isnull=False)), name='notification_read_state_consistent'),
                ],
            },
        ),
    ]
