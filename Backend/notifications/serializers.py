from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    metadata = serializers.JSONField(source='public_metadata', read_only=True)

    class Meta:
        model = Notification
        fields = (
            'id', 'type', 'priority', 'title', 'message', 'is_read', 'read_at',
            'created_at', 'source_domain', 'source_type', 'source_id', 'event_code',
            'metadata',
        )
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    unread_count = serializers.IntegerField(read_only=True)


class ReadAllResultSerializer(serializers.Serializer):
    updated_count = serializers.IntegerField(read_only=True)
