import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('profiles', '0003_assignment_history_and_integrity'),
    ]

    operations = [
        migrations.CreateModel(
            name='MedicalAuditEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor_reference', models.UUIDField(blank=True, editable=False, null=True)),
                ('actor_role', models.CharField(blank=True, max_length=20)),
                ('patient_reference', models.UUIDField(blank=True, editable=False, null=True)),
                ('action', models.CharField(choices=[('VIEW', 'View'), ('LIST', 'List'), ('CREATE', 'Create'), ('UPDATE', 'Update'), ('DOWNLOAD', 'Download'), ('ACCESS_DENIED', 'Access denied')], max_length=20)),
                ('result', models.CharField(choices=[('SUCCESS', 'Success'), ('DENIED', 'Denied')], default='SUCCESS', max_length=10)),
                ('domain', models.CharField(choices=[('MONITORING', 'Monitoring'), ('MEDICAL_RECORDS', 'Medical records')], max_length=30)),
                ('resource_type', models.CharField(max_length=100)),
                ('resource_id', models.UUIDField(blank=True, null=True)),
                ('http_method', models.CharField(blank=True, max_length=10)),
                ('endpoint', models.CharField(blank=True, max_length=255)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=512)),
                ('request_id', models.UUIDField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('changes', models.JSONField(blank=True, default=dict)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medical_audit_events', to=settings.AUTH_USER_MODEL)),
                ('patient', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='medical_audit_events', to='profiles.patientprofile')),
            ],
            options={
                'ordering': ('-created_at',),
                'indexes': [
                    models.Index(fields=['-created_at'], name='audit_created_idx'),
                    models.Index(fields=['actor', '-created_at'], name='audit_actor_date_idx'),
                    models.Index(fields=['patient', '-created_at'], name='audit_patient_date_idx'),
                    models.Index(fields=['resource_type', 'resource_id'], name='audit_resource_idx'),
                    models.Index(fields=['action', '-created_at'], name='audit_action_date_idx'),
                    models.Index(fields=['result', '-created_at'], name='audit_result_date_idx'),
                ],
            },
        ),
    ]
