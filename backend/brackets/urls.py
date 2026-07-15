from django.urls import path

from brackets import views

urlpatterns = [
    path('tournaments/<int:pk>/brackets/', views.TournamentBracketView.as_view()),
    path('tournaments/<int:pk>/matches/', views.TournamentMatchesView.as_view()),
    path('matches/<int:pk>/', views.MatchDetailView.as_view()),
    path('matches/<int:pk>/result/', views.MatchResultView.as_view()),
]
