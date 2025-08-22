from django.urls import path
from .views import RegisterView, LoginView, UserDetailView
from .views import UpdateProfileView


urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('', UserDetailView.as_view(), name='user-detail'),
    path('update-profile/', UpdateProfileView.as_view(), name='update-profile'),
]
