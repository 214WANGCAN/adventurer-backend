from rest_framework.pagination import PageNumberPagination

class TaskPagination(PageNumberPagination):
    page_size = 4  # 每页返回 4 个任务
    page_size_query_param = 'page_size'  # 可选，允许客户端自定义每页数量
    max_page_size = 100
