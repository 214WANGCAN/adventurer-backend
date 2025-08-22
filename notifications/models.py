from django.db import models
from django.conf import settings
from django.utils import timezone

class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('invite', '组队邀请'),
        ('system', '系统公告'),
        ('level_up', '等级提升'),
        ('task_update', '任务状态变更'),
        ('cancel_request', '取消任务请求'),
        ('completed', '任务已完成'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    related_task = models.ForeignKey('tasks.Task', on_delete=models.CASCADE, null=True, blank=True)
    related_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='related_notifications'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.get_type_display()} - {self.message[:30]}"
