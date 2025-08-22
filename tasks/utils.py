# tasks/utils.py
from .models import Task

def active_task_count(user):
    # 未完成的、我已接取的任务数量
    return Task.objects.filter(accepted_by=user, is_completed=False).count()
