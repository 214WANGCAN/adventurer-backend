from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from .serializers import UserSerializer
from django.contrib.auth import get_user_model
from rest_framework.permissions import AllowAny
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

User = get_user_model()

class RegisterView(APIView):
    def post(self, request):
        data = request.data
        if User.objects.filter(username=data.get('username')).exists():
            return Response({'error': '用户名已存在'}, status=400)
        
        user = User.objects.create_user(
            username=data['username'],
            email=data.get('email', ''),
            password=data['password'],
            nickname=data.get('nickname', '')
        )
        return Response({'message': '注册成功'}, status=201)

class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]   # 必须登录
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        user = request.user  # 当前登录用户
        nickname = request.data.get("nickname")
        avatar = request.data.get("avatar")
        
        # 校验 nickname
        if nickname is not None:
            if len(nickname) > 50:
                return Response({
                    "message": "昵称长度不能超过50个字符"
                }, status=status.HTTP_400_BAD_REQUEST)
            user.nickname = nickname

        # 校验 avatar
        if avatar is not None:
            if len(avatar) > 50:
                return Response({
                    "message": "头像地址长度不能超过50个字符"
                }, status=status.HTTP_400_BAD_REQUEST)
            user.avatar = avatar

        user.save()
        return Response({
            "message": "资料更新成功",
            "user": UserSerializer(user).data
        }, status=status.HTTP_200_OK)

class LoginView(APIView):
    permission_classes = [AllowAny]         # ✅ 允许所有人访问
    authentication_classes = []             # ✅ 禁用认证（登录时不需要）
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh_token': str(refresh),
                'access_token': str(refresh.access_token),
                'username': user.username
            })
        return Response({'error': '用户名或密码错误'}, status=status.HTTP_401_UNAUTHORIZED)

class UserDetailView(APIView):
    permission_classes = [AllowAny]  # 允许匿名访问，但使用 me=true 时需要认证
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        username = request.query_params.get('username')
        identifier = request.query_params.get('identifier')
        me = request.query_params.get('me')

        if me:  # 请求 me=true
            if request.user.is_authenticated:
                user = request.user
            else:
                return Response(
                    {'error': '未登录，无法获取当前用户信息'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
        elif username:
            user = get_object_or_404(User, username=username)
        elif identifier:
            user = get_object_or_404(User, identifier=identifier)
        else:
            return Response(
                {'error': '请提供 username、identifier 或 me=true 之一'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = UserSerializer(user)
        return Response(serializer.data)
