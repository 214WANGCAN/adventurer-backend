# tasks/serializers.py

from rest_framework import serializers
from .models import Task

class TaskSerializer(serializers.ModelSerializer):
    publisher_nickname = serializers.CharField(source='publisher.nickname', read_only=True)
    publisher_avatar = serializers.CharField(source='publisher.avatar', read_only=True)
    deadline = serializers.DateTimeField(format="%Y-%m-%d %H:%M")  # 自定义显示格式


    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'task_type', 'deadline',
            'experience_reward', 'token_reward', 'volunteerTime_reward', 'publisher_nickname', 'publisher_avatar', 'is_accepted','required_level'
        ]

class TaskDetailSerializer(serializers.ModelSerializer):
    publisher = serializers.StringRelatedField()
    accepted_by = serializers.StringRelatedField(many=True)
    invited_users = serializers.StringRelatedField(many=True)
    leader = serializers.StringRelatedField()

    class Meta:
        model = Task
        fields = '__all__'
