# from django.urls import path
# from .views import TaskListCreateView, TaskDetailView

# urlpatterns = [
#     path('tasks/', TaskListCreateView.as_view(), name='task-list-create'),
#     path('tasks/<int:id>/', TaskDetailView.as_view(), name='task-detail'),
# ]
# tasks/urls.py

from django.urls import path
from .views import *

urlpatterns = [
    path('', TaskListView.as_view()),
    path('create/', TaskCreateView.as_view()),

    path('<int:taskid>/', TaskDetailView.as_view()),
    path('<int:taskid>/apply/', ApplyTaskView.as_view()),
    path('<int:taskid>/accept/', AcceptInvitationView.as_view()),
    path('<int:taskid>/reject/', RejectInvitationView.as_view()),
    path('<int:taskid>/cancel/', RequestCancelTaskView.as_view()),
    path('<int:taskid>/approve-cancel/', ApproveCancelTaskView.as_view()),
    path('<int:taskid>/complete/', ApproveCompleteTaskView.as_view()),
    path('my-tasks/', MyTasksView.as_view(), name='my-tasks'),
    path('<int:taskid>/urge-approval/', UrgeApprovalView.as_view(), name='urge-approval'),
    path('<int:taskid>/remove-student/', RemoveParticipantFromSoloTaskView.as_view(), name='remove-student'),
    path('<int:taskid>/reject-cancel/', RejectCancelTaskView.as_view()),
    path('<int:taskid>/reject-complete/', RejectCompleteTaskView.as_view()),

]
