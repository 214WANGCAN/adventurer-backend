# notifications/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from .models import Notification
from .serializers import NotificationSerializer
from django.conf import settings

class TestCreateNotificationView(APIView):
    """测试用：创建一条通知"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # 防止生产环境使用
        if not settings.DEBUG:
            return Response({'error': '生产环境禁止使用此接口'}, status=status.HTTP_403_FORBIDDEN)

        from .models import Notification

        notification = Notification.objects.create(
            user=request.user,
            type=request.data.get('type', 'system'),
            message=request.data.get('message', '这是一条测试通知'),
            related_user=request.user if request.data.get('with_related_user') else None
        )

        return Response({
            'message': '测试通知已创建',
            'notification_id': notification.id
        }, status=status.HTTP_201_CREATED)


class LatestNotificationsView(APIView):
    """获取最近 10 条通知（全部，不管是否已读）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        notifications = Notification.objects.filter(user=user).order_by('-created_at')[:10]
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data)


class UnreadNotificationsView(APIView):
    """获取所有未读通知"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        unread_notifications = Notification.objects.filter(user=user, is_read=False).order_by('-created_at')
        serializer = NotificationSerializer(unread_notifications, many=True)
        return Response(serializer.data)


class MarkAllAsReadView(APIView):
    """将所有通知标记为已读"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        updated_count = Notification.objects.filter(user=user, is_read=False).update(is_read=True)
        return Response({'message': f'{updated_count} 条通知已标记为已读'}, status=status.HTTP_200_OK)

class MarkNotificationAsReadView(APIView):
    """将某个通知标记为已读"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(pk=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({'error': '通知不存在'}, status=status.HTTP_404_NOT_FOUND)

        if notification.is_read:
            return Response({'message': '该通知已是已读状态'}, status=status.HTTP_200_OK)

        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({'message': '通知已标记为已读'}, status=status.HTTP_200_OK)
