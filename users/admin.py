from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import CustomUser, UserTitle

@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    model = CustomUser
    list_display = ('username', 'identifier', 'role', 'nickname', 'email', 'level', 'experience', 'tokens', 'is_staff')
    list_filter = ('role', 'level', 'is_staff')
    search_fields = ('username', 'nickname', 'email', 'identifier')
    ordering = ('-experience',)
    readonly_fields = ('identifier',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('个人信息', {
            'fields': ('nickname', 'email', 'avatar', 'bio', 'experience', 'tokens', 'level', 'identifier', 'title', 'role')
        }),
        ('权限设置', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('其他', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'role'),  # 添加 role 到新增表单
        }),
    )

@admin.register(UserTitle)
class UserTitleAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
