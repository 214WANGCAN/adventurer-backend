# apps/qrcode_api/urls.py
from django.urls import path
from .views import ComposeQrOnBaseView

urlpatterns = [
    path("compose/", ComposeQrOnBaseView.as_view()),
]
