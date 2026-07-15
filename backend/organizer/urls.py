from django.urls import path

from organizer import views

urlpatterns = [
    path('organizer/register/', views.OrganizerRegisterView.as_view()),
    path('organizer/upload-cnic/', views.OrganizerUploadCnicView.as_view()),
    path('organizer/upload-company/', views.OrganizerUploadCompanyView.as_view()),
    path('organizer/status/', views.OrganizerStatusView.as_view()),
    path('organizer/profile/', views.OrganizerProfileView.as_view()),
    path('organizer/dashboard/', views.OrganizerDashboardView.as_view()),

    path('admin/organizers/', views.AdminOrganizerListView.as_view()),
    path('admin/organizers/<int:pk>/', views.AdminOrganizerDetailView.as_view()),
]
