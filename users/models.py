import random
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

from notifications.utils import create_notification
def generate_unique_user_id():
    while True:
        user_id = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        if user_id[0] != '0' and not CustomUser.objects.filter(identifier=user_id).exists():
            return user_id

class UserTitle(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

def avatar_upload_path(instance, filename):
    return f'avatars/user_{instance.id}/{filename}'

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('student', '学生/冒险者'),
        ('teacher', '老师'),
        ('admin', '系统管理员')
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')

    nickname = models.CharField(max_length=50)
    realname = models.CharField(max_length=50,default="none")
    avatar = models.CharField(max_length=50,default='none')
    bio = models.TextField(blank=True, null=True, help_text="个性签名 / 冒险者自我介绍")
    experience = models.PositiveIntegerField(default=0)
    tokens = models.PositiveIntegerField(default=0)
    volunteerTime = models.FloatField(default=0)
    credit_score = models.PositiveIntegerField(default=100)
    level = models.CharField(max_length=10, default='F')
    title = models.ForeignKey(UserTitle, on_delete=models.SET_NULL, null=True, blank=True)
    identifier = models.CharField(max_length=6, unique=True, editable=False, blank=True)
    

    def calculate_level(self):
        xp = self.experience
        if xp >= 50000 and self.title:
            return self.title.name
        # 从大到小遍历，找到符合的等级
        for threshold, lvl in reversed(settings.LEVEL_THRESHOLDS):
            if xp >= threshold:
                return lvl
        return 'F'

    def get_next_level_xp(self):
        """到下一级需要多少经验（满级返回 None）"""
        xp = self.experience
        for threshold, lvl in settings.LEVEL_THRESHOLDS:
            if xp < threshold:
                return threshold - xp
        return None

    def get_current_level_xp(self):
        """返回当前等级的最低经验值"""
        xp = self.experience
        current_threshold = 0
        for threshold, lvl in settings.LEVEL_THRESHOLDS:
            if xp >= threshold:
                current_threshold = threshold
        return current_threshold

    def save(self, *args, **kwargs):
        # 保存之前的等级，用来对比是否升级
        old_level = None
        if self.pk:  # pk 存在说明是更新，不是新建
            old_level = CustomUser.objects.filter(pk=self.pk).values_list('level', flat=True).first()

        # 如果没有 identifier 则生成一个
        if not self.identifier:
            self.identifier = generate_unique_user_id()

        self.level = self.calculate_level()
        super().save(*args, **kwargs)

        # 如果等级提升，发送通知
        if old_level and self.level != old_level:
            create_notification(
                user=self,
                type='level_up',
                message=f'恭喜你升级到 {self.level}！',
                task=None
            )

    def __str__(self):
        return self.nickname or self.username
