from django.db import models
from django.conf import settings


LEVEL_CHOICES = [lvl for _, lvl in settings.LEVEL_THRESHOLDS]


class Task(models.Model):
    TASK_TYPE_CHOICES = [
        ('solo', '个人'),
        ('team', '组队'),
    ]

    title = models.CharField(max_length=100)
    description = models.TextField()
    task_type = models.CharField(max_length=10, choices=TASK_TYPE_CHOICES)
    publisher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='published_tasks')
    
    maximum_users = models.PositiveIntegerField(default=1)
    required_level = models.CharField(max_length=10, choices=[(lvl, lvl) for lvl in LEVEL_CHOICES], default='F')

    experience_reward = models.PositiveIntegerField(default=0)
    token_reward = models.PositiveIntegerField(default=0)
    volunteerTime_reward = models.FloatField(default=0)

    image = models.ImageField(upload_to='task_images/', blank=True, null=True)
    deadline = models.DateTimeField()

    accepted_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='accepted_tasks',
        blank=True
    )

    invited_users = models.ManyToManyField(   # 新增，被邀请的用户列表
        settings.AUTH_USER_MODEL,
        related_name='invited_tasks',
        blank=True
    )

    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='led_tasks',
        blank=True,
        null=True,
        on_delete=models.SET_NULL
    )

    is_completed = models.BooleanField(default=False)
    is_expired = models.BooleanField(default=False)

    is_accepted = models.BooleanField(default=False)  # 新增，判断任务是否被接受
    is_started = models.BooleanField(default=False)  # 新增，判断任务是否开始

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # is_cancelled = models.BooleanField(default=False)  # 是否已被取消
    cancel_requested = models.BooleanField(default=False)  # 是否提出取消申请

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_task_type_display()}] {self.title}"


from django.db import models
from django.conf import settings
from django.db.models import Q

# models.py（与之前相同即可）
class TaskRequest(models.Model):
    TYPE_COMPLETION = 'completion'   # 催审核
    TYPE_CANCEL = 'cancel'           # 申请取消
    TYPE_CHOICES = [(TYPE_COMPLETION, '催审核'), (TYPE_CANCEL, '申请取消')]

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [(STATUS_PENDING, '待处理'), (STATUS_APPROVED, '已同意'), (STATUS_REJECTED, '已拒绝')]

    task = models.ForeignKey('Task', on_delete=models.CASCADE, related_name='requests')
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_requests')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['task', 'requester', 'type'],
                condition=models.Q(status='pending'),
                name='unique_pending_task_request_per_user_and_type'
            )
        ]
