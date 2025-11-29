from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('logout/', views.logout_view, name='logout'),

    # ใช้ Login ของ Django เอง (แค่สร้างไฟล์ templates/registration/login.html ก็ใช้ได้เลย)
    path('', auth_views.LoginView.as_view(template_name='users/login.html'), name='login'),
]