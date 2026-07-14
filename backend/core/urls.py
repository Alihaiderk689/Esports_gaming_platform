from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core import views

urlpatterns = [
    path('health/', views.health_check),

    path('auth/register/', views.RegisterView.as_view()),
    path('auth/login/', views.LoginView.as_view()),
    path('auth/google-login/', views.GoogleLoginView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('auth/token/refresh/', TokenRefreshView.as_view()),
    path('auth/forgot-password/', views.ForgotPasswordView.as_view()),
    path('auth/reset-password/', views.ResetPasswordView.as_view()),
    path('auth/verify-email/', views.VerifyEmailView.as_view()),
    path('auth/resend-verification/', views.ResendVerificationView.as_view()),
    path('auth/me/', views.ProfileView.as_view()),
    path('auth/change-password/', views.ChangePasswordView.as_view()),
]
