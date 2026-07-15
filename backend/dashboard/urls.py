from django.urls import path

from dashboard import views

urlpatterns = [
    path('dashboard/player/', views.PlayerDashboardView.as_view()),
    path('dashboard/organizer/', views.OrganizerDashboardView.as_view()),
    path('dashboard/admin/', views.AdminDashboardView.as_view()),
    path('dashboard/stats/', views.PlatformStatsView.as_view()),
]
