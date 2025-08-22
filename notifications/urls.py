# notifications/urls.py

from django.urls import path
from .views import LatestNotificationsView, UnreadNotificationsView, MarkAllAsReadView, MarkNotificationAsReadView, TestCreateNotificationView

urlpatterns = [
    path('latest/', LatestNotificationsView.as_view(), name='latest-notifications'),
    path('unread/', UnreadNotificationsView.as_view(), name='unread-notifications'),
    path('mark-all-read/', MarkAllAsReadView.as_view(), name='mark-all-read'),
    path('<int:pk>/mark-read/', MarkNotificationAsReadView.as_view(), name='mark-notification-read'),
    path('test-create/', TestCreateNotificationView.as_view(), name='test-create-notification'),
]