# notifications/utils.py

from .models import Notification

def create_notification(user, type, message, task=None):
    Notification.objects.create(
        user=user,
        type=type,
        message=message,
        related_task=task
    )
