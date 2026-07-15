from django.urls import path

from notifications import views

urlpatterns = [
    path('notifications/', views.NotificationListView.as_view()),
    path('notifications/read/', views.NotificationMarkReadView.as_view()),
    path('notifications/read-all/', views.NotificationMarkAllReadView.as_view()),
    path('notifications/<int:pk>/', views.NotificationDeleteView.as_view()),
]
