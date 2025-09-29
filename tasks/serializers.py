# tasks/serializers.py

from rest_framework import serializers
from .models import Task

from users.models import CustomUser  # 引入用户模型

class AcceptedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'nickname', 'realname', 'avatar']  # 只返回你关心的信息

class TaskSerializer(serializers.ModelSerializer):
    publisher_nickname = serializers.CharField(source='publisher.nickname', read_only=True)
    publisher_avatar = serializers.CharField(source='publisher.avatar', read_only=True)
    deadline = serializers.DateTimeField(format="%Y-%m-%d %H:%M")  # 自定义显示格式

    accepted_by = AcceptedUserSerializer(many=True, read_only=True)  # 嵌套序列化用户信息

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'task_type', 'maximum_users', 'deadline',
            'experience_reward', 'token_reward', 'volunteerTime_reward',
            'publisher_nickname', 'publisher_avatar',
            'accepted_by',  # 这里现在是对象数组，包含id、nickname、avatar
            'is_accepted', 'is_completed', 'required_level'
        ]
    
class TaskDetailSerializer(serializers.ModelSerializer):
    publisher = serializers.StringRelatedField()
    # accepted_by = serializers.StringRelatedField(many=True)
    invited_users = serializers.StringRelatedField(many=True)
    leader = serializers.StringRelatedField()
    publisher_nickname = serializers.CharField(source='publisher.nickname', read_only=True)
    publisher_avatar = serializers.CharField(source='publisher.avatar', read_only=True)
    accepted_by = AcceptedUserSerializer(many=True, read_only=True)  # 嵌套序列化用户信息

    class Meta:
        model = Task
        fields = '__all__'
