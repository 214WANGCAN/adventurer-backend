# apps/notifications/utils.py
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from .models import Notification

def create_notification(user, type, message, task=None, related_user=None, send_email=True):
    notification = Notification.objects.create(
        user=user,
        type=type,
        message=message,
        related_task=task,
        related_user=related_user
    )
    if send_email and getattr(user, "email", None):
        send_notification_email(notification)
    return notification


def _subject_for(notification: Notification) -> str:
    subjects = {
        'invite': '组队邀请',
        'system': '系统公告',
        'level_up': '等级提升通知',
        'task_update': '任务状态变更',
        'cancel_request': '取消任务请求',
        'completed': '任务已完成',
        'completion_request': '确认完成任务请求'
    }
    base = subjects.get(notification.type, '通知')
    return f"[冒险者工会] {base}"


def _build_context(notification: Notification) -> dict:
    site_url = getattr(settings, "SITE_URL", "https://example.com")

    task_url = None
    if notification.related_task_id:
        task_url = f"{site_url}/tasks/{notification.related_task_id}/"

    # 颜色主题（你指定的三色）
    theme = {
        "primary": "#2B2C57",  # 深色标题/按钮
        "bg": "#F4F7FE",       # 整体背景
        "card": "#FFFFFF"      # 卡片内容区
    }

    return {
        "user": notification.user,
        "notification": notification,
        "message": notification.message,
        "task_url": task_url,
        "site_url": site_url,
        "theme": theme,
    }


def send_notification_email(notification: Notification):
    subject = _subject_for(notification)
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")
    to = [notification.user.email]

    context = _build_context(notification)
    html_content = render_to_string("emails/notification_generic.html", context)

    # 纯文本降级：从 HTML 提取文本 + 附加关键链接
    text_fallback = strip_tags(html_content)
    if context.get("task_url"):
        text_fallback += f"\n\n查看任务：{context['task_url']}"
    text_fallback += f"\n访问网站：{context['site_url']}"

    msg = EmailMultiAlternatives(subject, text_fallback, from_email, to)
    msg.attach_alternative(html_content, "text/html")
    msg.send()
