# tasks/views.py

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Task
from .serializers import TaskSerializer, TaskDetailSerializer
from users.models import CustomUser  # 根据你的用户模块位置调整
from .pagination import TaskPagination
from notifications.utils import create_notification

from django.db.models import Case, When, Value, IntegerField
from django.utils import timezone
from rest_framework import generics
from django.conf import settings
# 头部导入补充
from django.db.models import Case, When, Value, IntegerField, Count, F

from .utils import active_task_count


def str_to_bool(value: str):
    if value is None:
        return None
    return value.lower() in {"1", "true", "t", "yes", "y"}

# 自定义权限类
class IsStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'student'

class IsTeacher(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'teacher'

class TaskListView(generics.ListAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TaskPagination

    def get_queryset(self):
        user = self.request.user
        user_level = user.calculate_level()

        # 等级顺序映射 {"F":0, "E":1, ..., "SSS":7}
        level_order = {lvl: i for i, (_, lvl) in enumerate(settings.LEVEL_THRESHOLDS)}
        user_level_index = level_order[user_level]

        params = self.request.query_params
        level_param = params.get("level")  # 例如 ?level=E
        is_completed_param = str_to_bool(params.get("is_completed"))  # ?is_completed=true/false
        is_accepted_param = str_to_bool(params.get("is_accepted"))    # ?is_accepted=true/false
        task_type_param = params.get("task_type")  # 可选：solo / team
        include_expired = str_to_bool(params.get("include_expired"))  # 可选：包含过期

        # 基础 queryset：默认仍按“未完成 + 未过期”
        qs = Task.objects.all()

        if is_completed_param is None:
            qs = qs.filter(is_completed=False)
        else:
            qs = qs.filter(is_completed=is_completed_param)

        if not include_expired:
            qs = qs.filter(deadline__gte=timezone.now())

        if level_param:
            # 仅当 level 合法时才筛选
            valid_levels = {lvl for _, lvl in settings.LEVEL_THRESHOLDS}
            if level_param in valid_levels:
                qs = qs.filter(required_level=level_param)

        if is_accepted_param is not None:
            qs = qs.filter(is_accepted=is_accepted_param)

        if task_type_param in {"solo", "team"}:
            qs = qs.filter(task_type=task_type_param)

        # 注解 + 排序逻辑与原先一致
        qs = qs.annotate(
            # 是否高于用户等级：高于则 1，否则 0
            above_user_level=Case(
                When(
                    required_level__in=[lvl for lvl, idx in level_order.items() if idx > user_level_index],
                    then=Value(1)
                ),
                default=Value(0),
                output_field=IntegerField()
            ),
            # 当前已接取人数
            accepted_count=Count("accepted_by", distinct=True),
            # 未满员的 solo 任务排前；其他仍按 is_accepted 排序
            accepted_order=Case(
                When(task_type="solo", accepted_count__lt=F("maximum_users"), then=Value(0)),
                When(is_accepted=False, then=Value(0)),
                default=Value(1),
                output_field=IntegerField()
            ),
        ).order_by("above_user_level", "accepted_order", "-created_at")

        return qs

# 发布任务（老师）
class TaskCreateView(generics.CreateAPIView):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, IsTeacher]

    def perform_create(self, serializer):
        serializer.save(publisher=self.request.user)

# 任务详情
class TaskDetailView(generics.RetrieveAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskDetailSerializer
    permission_classes = []
    lookup_field = 'id'
    lookup_url_kwarg = 'taskid'

class ApplyTaskView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if task.is_completed:
            return Response({'detail': '任务已结束'}, status=400)

        if task.task_type == "team" and task.leader is not None or task.maximum_users <= task.accepted_by.count():
            return Response({'detail': '任务已被他人申请'}, status=400)

        if active_task_count(request.user) >= getattr(settings, 'MAX_ACTIVE_TASKS', 6):
            return Response({'detail': '你已达到同时进行任务的上限（6个）'}, status=403)

        # 从请求中获取 invited_identifiers（使用 identifier 而不是数据库 id）
        invited_identifiers = request.data.get('invited_identifiers', [])
        task.accepted_by.add(request.user)

        if task.task_type == 'solo':
            task.is_started = True
            task.is_accepted = True

        elif task.task_type == 'team':
            task.leader = request.user
            if not invited_identifiers:
                task.is_started = True
                task.is_accepted = True
            else:
                users = CustomUser.objects.filter(identifier__in=invited_identifiers)
                if users.count() != len(invited_identifiers):
                    return Response({'detail': '部分 identifier 无效或用户不存在'}, status=400)

                task.invited_users.set(users)
                task.is_accepted = True

                # 给被邀请者发送通知
                for user in users:
                    create_notification(
                        user=user,
                        type='invite',
                        message=f'你被 {request.user.nickname or request.user.username} 邀请加入任务《{task.title}》',
                        task=task
                    )

        task.save()
        return Response({'detail': '任务已申请成功'}, status=200)


# 接受邀请（学生）
class AcceptInvitationView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if request.user not in task.invited_users.all():
            return Response({'detail': '你未被邀请'}, status=403)

        # ✅ 新增：限制未完成任务数量
        if active_task_count(request.user) >= getattr(settings, 'MAX_ACTIVE_TASKS', 6):
            return Response({'detail': '你已达到同时进行任务的上限（6个）'}, status=403)

        task.invited_users.remove(request.user)
        task.accepted_by.add(request.user)
        task.save()
        return Response({'detail': '已接受邀请'}, status=200)

# 拒绝邀请（学生）
class RejectInvitationView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if request.user in task.invited_users.all():
            task.invited_users.remove(request.user)
            return Response({'detail': '已拒绝邀请'}, status=200)
        return Response({'detail': '你未被邀请'}, status=403)

# 队长邀请队员
# class InviteUserView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, taskid):
#         task = get_object_or_404(Task, id=taskid)

#         if task.leader != request.user:
#             return Response({'detail': '只有队长可以邀请'}, status=403)

#         user_id = request.data.get('user_id')
#         if not user_id:
#             return Response({'detail': '缺少 user_id'}, status=400)

#         try:
#             user = CustomUser.objects.get(id=user_id)
#             task.invited_users.add(user)
#             return Response({'detail': f'已邀请 {user.nickname or user.username}'}, status=200)
#         except CustomUser.DoesNotExist:
#             return Response({'detail': '用户不存在'}, status=404)

# 队长申请取消任务
class RequestCancelTaskView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        # Solo tasks can be canceled by any participant, not just the leader
        if task.task_type == 'solo' or task.leader == request.user:
            # Ensure summary and detail are provided
            summary = request.data.get('summary')
            detail = request.data.get('detail')
            if not summary or not detail:
                return Response({'detail': '取消申请必须提供 summary 和 detail'}, status=400)

            # Set cancel_requested to True and save the request
            if task.task_type == 'team':
                task.cancel_requested = True
                task.save()

            # Send a notification to the teacher
            teacher = task.publisher
            if teacher and teacher.role == 'teacher':
                create_notification(
                    user=teacher,
                    type='cancel_request',
                    message=f'{request.user.nickname or request.user.username}♪{task.title}♪{summary}♪{detail}',
                    task=task
                )

            return Response({'detail': '取消申请已提交，请等待审核'}, status=200)

        return Response({'detail': '只有队长或单人任务参与者才能申请取消'}, status=403)

class RemoveParticipantFromSoloTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        # Ensure the task is solo and is not already canceled
        if task.task_type != 'solo' or task.is_completed:
            return Response({'detail': '此任务无法移除参与者'}, status=400)

        # Get the user to be removed
        participant_id = request.data.get('participant_id')
        if not participant_id:
            return Response({'detail': '缺少 participant_id'}, status=400)

        participant = get_object_or_404(CustomUser, id=participant_id)

        # Ensure the participant is in the task
        if participant not in task.accepted_by.all():
            return Response({'detail': '该用户不在任务中'}, status=400)

        # Remove the participant
        task.accepted_by.remove(participant)

        # If no participants left, mark task as canceled
        if task.accepted_by.count() == 0:
            task.is_completed = True
            task.is_accepted = False
            task.cancel_requested = True  # Mark it as canceled
            task.save()

            # Send a notification to the teacher
            create_notification(
                user=task.publisher,
                type='task_canceled',
                message=f'任务《{task.title}》因没有参与者被取消',
                task=task
            )

            return Response({'detail': '任务已被取消，参与者已移除'}, status=200)

        task.save()

        return Response({'detail': f'{participant.nickname or participant.username} 已被移除'}, status=200)


class ApproveCancelTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if not task.cancel_requested:
            return Response({'detail': '未收到取消申请'}, status=400)

        # 重置任务状态
        task.leader = None
        task.accepted_by.clear()
        task.invited_users.clear()
        task.is_started = False
        task.is_accepted = False
        task.cancel_requested = False  # ✅ 清除申请状态
        task.save()

        return Response({'detail': '任务取消申请已批准，任务已重置为未被接取'}, status=200)

class ApproveCompleteTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if task.is_completed:
            return Response({'detail': '任务已完成'}, status=400)

        # 标记任务完成
        task.is_completed = True
        task.save()

        # 单人任务直接加经验和代币
        if task.task_type == 'solo':
            participants = task.accepted_by.all()
            for student in participants:
                student.experience += task.experience_reward
                student.tokens += task.token_reward
                student.volunteerTime += task.volunteerTime_reward
                student.save()

        # 多人任务逻辑以后再补充
        elif task.task_type == 'team':
            pass

        return Response({'detail': '任务已完成'}, status=200)
    
class MyTasksView(generics.ListAPIView):
    """根据用户身份返回“我的任务”：
    - 学生：我接取的任务
    - 老师：我发布的任务
    支持 ?is_completed=true/false（默认 false）
    """
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # 和上面列表接口保持一致的布尔参数解析
        def _str_to_bool(v: str):
            if v is None:
                return None
            return v.lower() in {"1", "true", "t", "yes", "y"}

        is_completed_param = _str_to_bool(self.request.query_params.get("is_completed"))

        qs = Task.objects.all()

        # 默认只看未完成
        if is_completed_param is None:
            pass
        else:
            qs = qs.filter(is_completed=is_completed_param)

        # 按身份切换筛选字段
        if getattr(user, "role", None) == "teacher":
            qs = qs.filter(publisher=user)
        else:
            # 默认为学生/其他：看我接取的
            qs = qs.filter(accepted_by=user)

        return qs.order_by("-created_at")

# —— 追加到文件尾部或合适位置 ——
class UrgeApprovalView(APIView):
    """学生催促老师审核任务完成"""
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        # 任务已完成就不需要催促
        if task.is_completed:
            return Response({'detail': '任务已完成，无需催促'}, status=400)

        # 必须是该任务的参与者
        if request.user not in task.accepted_by.all():
            return Response({'detail': '你未参与该任务，不能催促'}, status=403)

        # 团队任务默认只允许队长催促（如需放开可去掉该判断）
        if task.task_type == 'team' and task.leader != request.user:
            return Response({'detail': '仅队长可以发起催促'}, status=403)

        teacher = getattr(task, 'publisher', None)
        if teacher is None or getattr(teacher, 'role', None) != 'teacher':
            return Response({'detail': '任务没有有效的老师发布者'}, status=400)

        # 发送通知
        create_notification(
            user=teacher,
            type='completion_request',  # 你可在前端按 type 做分类展示
            message=f'{request.user.nickname or request.user.username} 请求你审核任务《{task.title}》的完成情况',
            task=task
        )

        return Response({'detail': '已通知老师尽快审核'}, status=200)
