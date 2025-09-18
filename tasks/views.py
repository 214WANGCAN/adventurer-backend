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
from .models import Task, TaskRequest
from .utils import active_task_count
from django.db import transaction  # 可选：保证一致性
# tasks/views.py 顶部工具
def sync_task_cancel_flag(task):
    from .models import TaskRequest  # 避免循环导入
    has_pending_cancel = TaskRequest.objects.filter(
        task=task, type=TaskRequest.TYPE_CANCEL, status=TaskRequest.STATUS_PENDING
    ).exists()
    if task.cancel_requested != has_pending_cancel:
        task.cancel_requested = has_pending_cancel
        task.save(update_fields=['cancel_requested'])


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

#编辑任务
# —— 放在本文件合适位置（例如其他 View 后）——

class TaskUpdateView(generics.UpdateAPIView):
    """
    编辑任务（仅发布者老师可改）
    - 支持 PUT / PATCH（建议 PATCH 部分更新）
    - 关键校验：
        * 已完成任务不可编辑
        * 若任务已被接取（is_accepted=True），不允许修改 task_type
        * maximum_users 不可小于当前已接取人数
        * deadline 不可早于当前时间
        * required_level 必须是合法等级
        * 奖励数值不可为负
    - 成功后通知当前参与者/受邀者
    """
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, IsTeacher]
    lookup_field = 'id'
    lookup_url_kwarg = 'taskid'

    def get_queryset(self):
        # 只允许老师编辑自己发布的任务
        return Task.objects.filter(publisher=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        # 让 PATCH 默认走 partial=True
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        task: Task = self.get_object()

        if task.is_completed:
            return Response({'detail': '任务已完成，无法编辑'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()

        # —— 业务校验 —— 
        # 1) 不允许在已被接取后改任务类型
        if 'task_type' in data and str(data['task_type']) != str(task.task_type) and task.is_accepted:
            return Response({'detail': '任务已被接取，不可更改任务类型'}, status=status.HTTP_400_BAD_REQUEST)

        # 2) maximum_users 不可小于当前已接取人数
        if 'maximum_users' in data:
            try:
                new_max = int(data['maximum_users'])
            except (TypeError, ValueError):
                return Response({'detail': 'maximum_users 必须是整数'}, status=status.HTTP_400_BAD_REQUEST)
            if new_max < task.accepted_by.count():
                return Response({'detail': 'maximum_users 不可小于已接取人数'}, status=status.HTTP_400_BAD_REQUEST)
            if new_max < 1:
                return Response({'detail': 'maximum_users 必须 ≥ 1'}, status=status.HTTP_400_BAD_REQUEST)

        # 3) deadline 不可改到过去
        if 'deadline' in data and data['deadline']:
            # 若前端传 ISO 字符串，交给序列化器解析；这里做一个软校验
            try:
                # 如果你们的序列化器能正确解析时区，这里也可以省略
                from django.utils.dateparse import parse_datetime
                _dt = parse_datetime(data['deadline'])
                if _dt and _dt < timezone.now():
                    return Response({'detail': 'deadline 不能早于当前时间'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                pass

        # 4) required_level 合法性
        if 'required_level' in data:
            valid_levels = {lvl for _, lvl in settings.LEVEL_THRESHOLDS}
            if data['required_level'] not in valid_levels:
                return Response({'detail': 'required_level 非法'}, status=status.HTTP_400_BAD_REQUEST)

        # 5) 奖励字段非负
        for field in ('experience_reward', 'token_reward', 'volunteerTime_reward'):
            if field in data:
                try:
                    if int(data[field]) < 0:
                        return Response({'detail': f'{field} 不能为负数'}, status=status.HTTP_400_BAD_REQUEST)
                except (TypeError, ValueError):
                    return Response({'detail': f'{field} 必须是整数'}, status=status.HTTP_400_BAD_REQUEST)

        # —— 执行更新（支持 PUT / PATCH）——
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(task, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # —— 通知当前参与者与受邀者（可选，但很有用）——
        try:
            changed_fields = list(serializer.validated_data.keys())
            if changed_fields:
                # 给已接取与受邀的同学各发一条系统通知
                targets = list(task.accepted_by.all()) + list(task.invited_users.all())
                for u in targets:
                    create_notification(
                        user=u,
                        type='system',
                        message=f'任务《{task.title}》已被老师更新：{", ".join(changed_fields)}',
                        task=task,
                        related_user=request.user
                    )
        except Exception:
            # 静默忽略通知失败，确保核心更新成功
            pass

        return Response(serializer.data, status=status.HTTP_200_OK)


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

        # 🚫 防止重复申请
        if request.user in task.accepted_by.all():
            return Response({'detail': '你已接取过该任务，不能重复接取'}, status=400)


        # 从请求中获取 invited_identifiers（使用 identifier 而不是数据库 id）
        invited_identifiers = request.data.get('invited_identifiers', [])
        task.accepted_by.add(request.user)

        if task.task_type == 'solo':
            task.is_started = True
            # ✅ 只有人数满了才设置 is_accepted
            if task.accepted_by.count() >= task.maximum_users:
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
        
        # ✅ 新增：通知发布老师，有学生接取了任务
        teacher = getattr(task, 'publisher', None)
        if teacher and getattr(teacher, 'role', None) == 'teacher':
            create_notification(
                user=teacher,
                type='system',
                message=f'{request.user.nickname or request.user.username} 接取了你的任务《{task.title}》',
                task=task,
                related_user=request.user
            )

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


class RequestCancelTaskView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        # solo：参与者可申请；team：队长可申请
        if not (task.task_type == 'solo' or task.leader == request.user):
            return Response({'detail': '只有队长或单人任务参与者才能申请取消'}, status=403)

        summary = request.data.get('summary')
        detail = request.data.get('detail')
        if not summary or not detail:
            return Response({'detail': '取消申请必须提供 summary 和 detail'}, status=400)

        # ✅ 每个参与者各自只能有一个 pending 的取消申请
        exists_pending = TaskRequest.objects.filter(
            task=task, requester=request.user,
            type=TaskRequest.TYPE_CANCEL,
            status=TaskRequest.STATUS_PENDING
        ).exists()
        if exists_pending:
            return Response({'detail': '你已提交过取消申请，等待老师处理'}, status=400)

        TaskRequest.objects.create(
            task=task, requester=request.user,
            type=TaskRequest.TYPE_CANCEL,
            status=TaskRequest.STATUS_PENDING
        )

        # ✅ 任务层面的“有待处理取消申请”标志
        task.cancel_requested = True
        task.save(update_fields=['cancel_requested'])

        teacher = task.publisher
        if teacher and teacher.role == 'teacher':
            create_notification(
                user=teacher,
                type='cancel_request',
                message=(
                    f"{request.user.nickname or request.user.username} 请求取消任务《{task.title}》"
                    f"\n原因：{summary}\n详情：{detail}"
                ),
                task=task,
                related_user=request.user
            )

        return Response({'detail': '取消申请已提交，请等待审核'}, status=200)

class RemoveParticipantFromSoloTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    @transaction.atomic
    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if task.task_type != 'solo' or task.is_completed:
            return Response({'detail': '此任务无法移除参与者'}, status=400)

        participant_id = request.data.get('participant_id')
        if not participant_id:
            return Response({'detail': '缺少 participant_id'}, status=400)

        participant = get_object_or_404(CustomUser, id=participant_id)

        if participant not in task.accepted_by.all():
            return Response({'detail': '该用户不在任务中'}, status=400)

        task.accepted_by.remove(participant)

        # ✅ 新增：通知被移除者
        create_notification(
            user=participant,
            type='system',
            message=f'你已被移出任务《{task.title}》',
            task=task,
            related_user=request.user  # 老师
        )

        TaskRequest.objects.filter(task=task, requester=participant).delete()

        if task.accepted_by.count() == 0:
            TaskRequest.objects.filter(task=task).delete()

            task.is_completed = True
            task.is_accepted = False
            task.cancel_requested = True
            task.save()

            # 已有：通知老师任务被取消
            create_notification(
                user=task.publisher,
                type='system',
                message=f'任务《{task.title}》因没有参与者被取消',
                task=task
            )

            return Response({'detail': '任务已被取消，参与者及相关请求已清空'}, status=200)

        return Response({'detail': f'{participant.nickname or participant.username} 已被移除，相关请求已清空'}, status=200)


class ApproveCancelTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        # 没有任何 pending 取消就不处理
        if not TaskRequest.objects.filter(task=task, type=TaskRequest.TYPE_CANCEL, status=TaskRequest.STATUS_PENDING).exists():
            return Response({'detail': '未收到取消申请'}, status=400)

        # 重置任务
        task.leader = None
        task.accepted_by.clear()
        task.invited_users.clear()
        task.is_started = False
        task.is_accepted = False
        task.is_completed = False
        task.cancel_requested = False
        task.save()

        # 所有“取消申请”的待处理请求记为已同意
        TaskRequest.objects.filter(
            task=task, type=TaskRequest.TYPE_CANCEL, status=TaskRequest.STATUS_PENDING
        ).update(status=TaskRequest.STATUS_APPROVED)

        return Response({'detail': '任务取消申请已批准，任务已重置为未被接取'}, status=200)


class ApproveCompleteTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if task.is_completed:
            return Response({'detail': '任务已完成'}, status=200)

        task.is_completed = True
        task.save()

        # 先记录当前参与者列表（发通知用）
        participants = list(task.accepted_by.all())

        if task.task_type == 'solo':
            for student in participants:
                student.experience += task.experience_reward
                student.tokens += task.token_reward
                student.volunteerTime += task.volunteerTime_reward
                student.save()
                # ✅ 新增：通知学生（包含奖励）
                create_notification(
                    user=student,
                    type='completed',
                    message=(
                        f'任务《{task.title}》已通过老师审核并完成！\n'
                        f'奖励：经验 +{task.experience_reward}、代币 +{task.token_reward}、志愿时长 +{task.volunteerTime_reward}'
                    ),
                    task=task
                )
        else:
            # ✅ 新增：团队任务也给所有参与者通知（不涉及发奖逻辑）
            for student in participants:
                create_notification(
                    user=student,
                    type='completed',
                    message=f'任务《{task.title}》已通过老师审核并完成！',
                    task=task
                )

        TaskRequest.objects.filter(
            task=task, type=TaskRequest.TYPE_COMPLETION, status=TaskRequest.STATUS_PENDING
        ).update(status=TaskRequest.STATUS_APPROVED)

        sync_task_cancel_flag(task)

        return Response({'detail': '任务已完成'}, status=200)



class RejectCancelTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)
        requester_id = request.data.get('requester_id')

        qs = TaskRequest.objects.filter(
            task=task, type=TaskRequest.TYPE_CANCEL, status=TaskRequest.STATUS_PENDING
        )
        if requester_id:
            qs = qs.filter(requester_id=requester_id)

        # 记录请求人
        req_users = list(CustomUser.objects.filter(
            id__in=qs.values_list('requester', flat=True)
        ))

        updated = qs.update(status=TaskRequest.STATUS_REJECTED)
        if updated == 0:
            return Response({'detail': '没有待处理的取消申请'}, status=400)

        sync_task_cancel_flag(task)

        # ✅ 新增：通知被拒绝者
        for u in req_users:
            create_notification(
                user=u,
                type='system',
                message=f'你对任务《{task.title}》的取消申请被老师拒绝',
                task=task
            )

        return Response({'detail': '已拒绝取消申请'}, status=200)


class RejectCompleteTaskView(APIView):
    permission_classes = [IsAuthenticated, IsTeacher]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)
        requester_id = request.data.get('requester_id')

        qs = TaskRequest.objects.filter(
            task=task, type=TaskRequest.TYPE_COMPLETION, status=TaskRequest.STATUS_PENDING
        )
        if requester_id:
            qs = qs.filter(requester_id=requester_id)

        # 记录请求人
        req_users = list(CustomUser.objects.filter(
            id__in=qs.values_list('requester', flat=True)
        ))

        updated = qs.update(status=TaskRequest.STATUS_REJECTED)
        if updated == 0:
            return Response({'detail': '没有待处理的催审核请求'}, status=400)

        # ✅ 新增：通知被拒绝者
        for u in req_users:
            create_notification(
                user=u,
                type='system',
                message=f'你对任务《{task.title}》的完成审核催促被老师拒绝',
                task=task
            )

        return Response({'detail': '已拒绝该任务的完成审核请求'}, status=200)


    
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
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, taskid):
        task = get_object_or_404(Task, id=taskid)

        if task.is_completed:
            return Response({'detail': '任务已完成，无需催促'}, status=400)

        # ✅ 任何参与者（accepted_by）都可催；不再限制队长
        if request.user not in task.accepted_by.all():
            return Response({'detail': '你未参与该任务，不能催促'}, status=403)

        teacher = getattr(task, 'publisher', None)
        if teacher is None or getattr(teacher, 'role', None) != 'teacher':
            return Response({'detail': '任务没有有效的老师发布者'}, status=400)

        # ✅ 每个参与者各自只能有一个 pending 的催促
        exists_pending = TaskRequest.objects.filter(
            task=task, requester=request.user,
            type=TaskRequest.TYPE_COMPLETION,
            status=TaskRequest.STATUS_PENDING
        ).exists()
        if exists_pending:
            return Response({'detail': '你已提交过催促，等待老师处理'}, status=400)

        TaskRequest.objects.create(
            task=task, requester=request.user,
            type=TaskRequest.TYPE_COMPLETION,
            status=TaskRequest.STATUS_PENDING
        )

        create_notification(
            user=teacher,
            type='completion_request',
            message=f'{request.user.nickname or request.user.username} 请求你审核任务《{task.title}》的完成情况',
            task=task,
            related_user=request.user
        )

        return Response({'detail': '已通知老师尽快审核'}, status=200)