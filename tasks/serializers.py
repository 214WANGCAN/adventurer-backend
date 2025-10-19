# tasks/serializers.py

from rest_framework import serializers
from .models import Task
from rest_framework.exceptions import ValidationError

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
    
    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        # 仅学生受此约束；老师逻辑保持不变
        if user and getattr(user, "role", None) == "student":
            token_reward = attrs.get("token_reward", 0)
            # 注意：严格小于（不能等于）
            if token_reward >= user.tokens:
                raise ValidationError({"token_reward": "学生发布任务的奖励必须小于你当前的代币余额。"})
        return attrs
    
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
