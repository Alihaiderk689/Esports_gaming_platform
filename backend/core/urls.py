from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core import views

urlpatterns = [
    path('health/', views.health_check),

    path('auth/register/', views.RegisterView.as_view()),
    path('auth/login/', views.LoginView.as_view()),
    path('auth/google/start/', views.GoogleOAuthStartView.as_view()),
    path('auth/google-login/', views.GoogleLoginView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('auth/logout-all/', views.LogoutAllSessionsView.as_view()),
    path('auth/token/refresh/', TokenRefreshView.as_view()),
    path('auth/forgot-password/', views.ForgotPasswordView.as_view()),
    path('auth/reset-password/', views.ResetPasswordView.as_view()),
    path('auth/verify-email/', views.VerifyEmailView.as_view()),
    path('auth/resend-verification/', views.ResendVerificationView.as_view()),
    path('auth/me/', views.ProfileView.as_view()),
    path('auth/change-password/', views.ChangePasswordView.as_view()),

    path('players/', views.PlayerListView.as_view()),
    path('players/top/', views.PlayerTopView.as_view()),
    path('players/following/', views.PlayerFollowingView.as_view()),
    path('players/me/', views.PlayerMeView.as_view()),
    path('players/<int:pk>/', views.PlayerDetailView.as_view()),
    path('players/<int:pk>/follow/', views.PlayerFollowView.as_view()),

    path('admin/users/', views.AdminUserListView.as_view()),
    path('admin/users/<int:pk>/', views.AdminUserDetailView.as_view()),

    path('disputes/mine/', views.DisputeMineView.as_view()),
    path('disputes/<int:pk>/', views.DisputeDetailView.as_view()),
    path('disputes/<int:pk>/evidence/', views.DisputeEvidenceUploadView.as_view()),
    path('disputes/<int:pk>/status/', views.DisputeStatusView.as_view()),
    path('disputes/<int:pk>/escalate/', views.DisputeEscalateView.as_view()),
    path('admin/disputes/', views.AdminDisputeListView.as_view()),
]
