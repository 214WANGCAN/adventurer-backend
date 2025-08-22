# notifications/serializers.py

from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    related_user_nickname = serializers.CharField(source='related_user.nickname', read_only=True)
    related_user_avatar = serializers.CharField(source='related_user.avatar', read_only=True)


    class Meta:
        model = Notification
        fields = ['id', 'type', 'message', 'is_read', 'created_at',
                  'related_task', 'related_user', 'related_user_nickname','related_user_avatar']