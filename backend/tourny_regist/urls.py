from django.urls import path

from tourny_regist import views

urlpatterns = [
    path('registrations/', views.RegistrationCreateView.as_view()),
    path('registrations/me/', views.MyRegistrationsView.as_view()),
    path('registrations/<int:pk>/', views.RegistrationDeleteView.as_view()),
    path('registrations/<int:pk>/check-in/', views.RegistrationCheckInView.as_view()),
    path('tournaments/<int:pk>/registrations/', views.TournamentRegistrationsView.as_view()),
]
