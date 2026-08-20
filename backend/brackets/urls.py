from django.urls import path

from brackets import views

urlpatterns = [
    path('tournaments/<int:pk>/brackets/', views.TournamentBracketView.as_view()),
    path('tournaments/<int:pk>/brackets/preview/', views.TournamentBracketPreviewView.as_view()),
    path('tournaments/<int:pk>/brackets/reset/', views.TournamentBracketResetView.as_view()),
    path('tournaments/<int:pk>/brackets/next-round/', views.TournamentNextRoundView.as_view()),
    path('tournaments/<int:pk>/brackets/generate-playoff/', views.TournamentGeneratePlayoffView.as_view()),
    path('tournaments/<int:pk>/matches/', views.TournamentMatchesView.as_view()),
    path('matches/<int:pk>/', views.MatchDetailView.as_view()),
    path('matches/<int:pk>/result/', views.MatchResultView.as_view()),
    path('matches/<int:pk>/override/', views.MatchOverrideView.as_view()),
    path('matches/<int:pk>/forfeit/', views.MatchForfeitView.as_view()),
    path('matches/<int:pk>/schedule/', views.MatchScheduleView.as_view()),
    path('matches/<int:pk>/notes/', views.MatchNotesView.as_view()),
    path('matches/<int:pk>/disputes/', views.MatchDisputeCreateView.as_view()),
]
