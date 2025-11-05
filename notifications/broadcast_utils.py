# apps/notifications/broadcast_utils.py

import time
import logging
from django.core.exceptions import PermissionDenied
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model

from .models import Notification
from .utils import _build_context  # 用你已有的模板样式逻辑

logger = logging.getLogger(__name__)

def _require_staff(actor):
    if actor is None or not (getattr(actor, "is_staff", False) or getattr(actor, "is_superuser", False)):
        raise PermissionDenied("仅管理员可执行群发通知。")


def _iter_chunked(queryset, chunk_size=500):
    iterator = queryset.iterator(chunk_size=chunk_size)
    chunk = []
    for obj in iterator:
        chunk.append(obj)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def broadcast_system_notification(
    actor,
    title: str,
    text_body: str,
    *,
    html_body: str | None = None,
    notification_type: str = "system",
    create_db_record: bool = True,
    send_email: bool = True,
    batch_size: int = 100,
    throttle_seconds: float = 0.0,
    fail_silently: bool = True,
    verbose: bool = True,   # ✅ 新增参数：控制是否打印进度
) -> dict:
    """
    群发系统通知到所有用户邮箱，并可选写 Notification 记录。
    """
    _require_staff(actor)

    User = get_user_model()
    qs = (
        User.objects.filter(is_active=True)
        .exclude(email__isnull=True)
        .exclude(email__exact="")
        .only("id", "email", "nickname", "realname")
        .order_by("id")
    )

    total_users = qs.count()
    emails_sent = 0
    notifications_created = 0

    subject_prefix = "[冒险者工会]"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "冒险者工会 <kingofemail@aidiventure.com>")
    site_url = getattr(settings, "SITE_URL", "https://www.aidiventure.com")

    timeout = getattr(settings, "EMAIL_TIMEOUT", 20)
    connection = get_connection(timeout=timeout)
    use_template = html_body is None

    if verbose:
        print(f"📬 开始群发：{total_users} 个用户，批次大小 {batch_size}...")

    connection.open()
    try:
        processed = 0
        for chunk in _iter_chunked(qs, chunk_size=batch_size):
            email_messages = []
            new_notifications = []

            for user in chunk:
                if create_db_record:
                    new_notifications.append(
                        Notification(
                            user=user,
                            type=notification_type,
                            message=text_body,
                            created_at=timezone.now(),
                        )
                    )

                if send_email:
                    notification_like = Notification(
                        user=user, type=notification_type, message=text_body
                    )
                    context = {
                        **_build_context(notification_like),
                        "user": user,
                        "notification": notification_like,
                        "message": text_body,
                        "task_url": None,
                        "site_url": site_url,
                    }

                    html_content = (
                        render_to_string("emails/notification_generic.html", context)
                        if use_template
                        else html_body
                    )

                    text_fallback = strip_tags(html_content)
                    text_fallback += f"\n\n访问网站：{site_url}"

                    msg = EmailMultiAlternatives(
                        f"{subject_prefix} {title}",
                        text_fallback,
                        from_email,
                        [user.email],
                        connection=connection,
                    )
                    msg.attach_alternative(html_content, "text/html")
                    email_messages.append(msg)

            # 批量写入 Notification
            if create_db_record and new_notifications:
                with transaction.atomic():
                    Notification.objects.bulk_create(new_notifications, batch_size=batch_size)
                    notifications_created += len(new_notifications)

            # 逐封发送（可打印每一封）
            if send_email and email_messages:
                for msg in email_messages:
                    try:
                        msg.send(fail_silently=fail_silently)
                        emails_sent += 1
                        processed += 1
                        if verbose:
                            print(f"✅ 已发送 {processed}/{total_users} → {msg.to[0]}")
                    except Exception as e:
                        logger.exception("发送失败: %s", e)
                        if not fail_silently:
                            raise
                        if verbose:
                            print(f"⚠️ 发送失败 → {msg.to[0]} ({e})")

            if throttle_seconds > 0:
                time.sleep(throttle_seconds)

    finally:
        try:
            connection.close()
        except Exception:
            pass

    summary = {
        "total_users": total_users,
        "emails_sent": emails_sent,
        "notifications_created": notifications_created,
    }
    if verbose:
        print(f"\n📦 群发完成！共发送 {emails_sent}/{total_users} 封邮件。")
    logger.info("Broadcast summary: %s", summary)
    return summary
# apps/notifications/broadcast_utils.py

def broadcast_system_notification_bcc(
    actor,
    title: str,
    text_body: str,
    *,
    html_body: str | None = None,
    notification_type: str = "system",
    message_en: str | None = None,
    create_db_record: bool = False,
    send_email: bool = True,
    bcc_batch_size: int = 80,        # 每封邮件的 BCC 人数（很多自建/商用 SMTP 建议 50~100 以内）
    throttle_seconds: float = 0.0,   # 每批次之间的停顿，避免触发限流
    fail_silently: bool = True,
    verbose: bool = True,
    to_address: str | None = None,   # 一些服务器要求必须有 To（收件人）字段，可指定一个展示地址
    reply_to: list[str] | None = None,
    target_role: str | None = None,
) -> dict:
    """
    按批次通过 BCC 群发系统通知。
    注意：BCC 群发无法对每个用户个性化渲染（例如昵称），模板中请勿使用 user 相关变量。
    """
    _require_staff(actor)

    User = get_user_model()
    qs = (
        User.objects.filter(is_active=True)
        .exclude(email__isnull=True)
        .exclude(email__exact="")
        .only("id", "email")  # 这里不再需要 nickname/realname
        .order_by("id")
    )

    # ✅ 根据角色过滤（新增逻辑）


    total_users = qs.count()
    emails_sent = 0
    notifications_created = 0

    subject_prefix = "[冒险者工会]"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "冒险者工会 <kingofemail@aidiventure.com>")
    site_url = getattr(settings, "SITE_URL", "https://www.aidiventure.com")
    timeout = getattr(settings, "EMAIL_TIMEOUT", 20)
    connection = get_connection(timeout=timeout)

    # 渲染一次（整批使用同一份内容）
    use_template = html_body is None

    if use_template:
        # 使用无个性化模板（不依赖 user / notification）
        base_context = {
            "title": title,
            "message": text_body,       # 中文或主语言内容
            "message_en": message_en,   # 英文内容（可选）
            "site_url": site_url,
        }
        html_content = render_to_string("emails/notification_broadcast.html", base_context)
    else:
        html_content = html_body

    text_fallback = strip_tags(html_content)
    if site_url not in text_fallback:
        text_fallback += f"\n\n访问网站：{site_url}"

    if verbose:
        print(f"📬 BCC 群发开始：{total_users} 个用户，单封 BCC 上限 {bcc_batch_size}...")

    connection.open()
    try:
        processed = 0

        # 为避免“数据库被锁”，将 DB 写入与发送分批进行；这里每批生成对应的 Notification
        for chunk in _iter_chunked(qs, chunk_size=bcc_batch_size):
            bcc_list = [u.email for u in chunk if u.email]

            # 先写入 Notification（可选）
            if create_db_record:
                new_notifications = [
                    Notification(
                        user=u,
                        type=notification_type,
                        message=text_body,
                        created_at=timezone.now(),
                    ) for u in chunk
                ]
                # 使用原子事务 + 较小批次，降低锁冲突概率
                with transaction.atomic():
                    Notification.objects.bulk_create(new_notifications, batch_size=200)
                notifications_created += len(new_notifications)

            # 发一封带 BCC 的邮件（可选）
            if send_email and bcc_list:
                try:
                    msg = EmailMultiAlternatives(
                        f"{subject_prefix} {title}",
                        text_fallback,
                        from_email,
                        [to_address or from_email],  # 某些 MTA 要求 To 不为空
                        bcc=bcc_list,
                        reply_to=reply_to or None,
                        connection=connection,
                    )
                    msg.attach_alternative(html_content, "text/html")
                    msg.send(fail_silently=fail_silently)

                    emails_sent += len(bcc_list)
                    processed += len(bcc_list)
                    if verbose:
                        print(f"✅ 已发送 {processed}/{total_users}（本批 {len(bcc_list)} 人）")
                except Exception as e:
                    logger.exception("BCC 批量发送失败: %s", e)
                    if not fail_silently:
                        raise
                    if verbose:
                        print(f"⚠️ 本批发送失败（{len(bcc_list)} 人）：{e}")

            if throttle_seconds > 0:
                time.sleep(throttle_seconds)

    finally:
        try:
            connection.close()
        except Exception:
            pass

    summary = {
        "total_users": total_users,
        "emails_sent": emails_sent,                 # 按收件人数统计
        "notifications_created": notifications_created,
        "bcc_batch_size": bcc_batch_size,
    }
    if verbose:
        print(f"\n📦 BCC 群发完成！共向 {emails_sent}/{total_users} 位用户投递（按 BCC 计数）。")
    logger.info("BCC Broadcast summary: %s", summary)
    return summary
