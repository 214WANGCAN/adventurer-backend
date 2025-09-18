from rest_framework import serializers
from .models import CustomUser, UserTitle

class UserTitleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTitle
        fields = ['identifier', 'name', 'description']

class UserSerializer(serializers.ModelSerializer):
    level = serializers.CharField(read_only=True)
    title = UserTitleSerializer(read_only=True)
    next_level_xp = serializers.SerializerMethodField()
    current_level_xp = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            'identifier', 'username', 'nickname', 'realname', 'email', 'avatar', 'bio',
            'experience', 'next_level_xp', 'current_level_xp' , 'tokens', 'volunteerTime', 'level', 'title', 'role',
        ]
    
    def get_next_level_xp(self, obj):
        return obj.get_next_level_xp()

    def get_current_level_xp(self, obj):
        return obj.get_current_level_xp()