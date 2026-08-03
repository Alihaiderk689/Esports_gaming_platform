from django.urls import path

from tourny_regist import views

urlpatterns = [
    path('tournaments/', views.TournamentListView.as_view()),
    path('tournaments/mine/', views.MyTournamentsView.as_view()),
    path('tournaments/<int:pk>/', views.TournamentDetailView.as_view()),
    path('tournaments/<int:pk>/publish/', views.TournamentPublishView.as_view()),
    path('tournaments/<int:pk>/announcements/', views.TournamentAnnouncementsView.as_view()),
    path('announcements/<int:pk>/', views.AnnouncementDeleteView.as_view()),
    path('tournaments/<int:pk>/champion-seen/', views.TournamentChampionSeenView.as_view()),

    path('admin/tournaments/', views.AdminTournamentListView.as_view()),
    path('admin/tournaments/<int:pk>/', views.AdminTournamentDetailView.as_view()),

    path('tournaments/<int:pk>/teams/', views.TeamCreateView.as_view()),
    path('tournaments/<int:pk>/teams/mine/', views.MyTeamView.as_view()),
    path('tournaments/<int:pk>/teams/join/', views.TeamJoinView.as_view()),
    path('teams/<int:pk>/leave/', views.TeamLeaveView.as_view()),
    path('teams/<int:pk>/register/', views.TeamRegisterView.as_view()),

    path('registrations/', views.RegistrationCreateView.as_view()),
    path('registrations/me/', views.MyRegistrationsView.as_view()),
    path('registrations/<int:pk>/', views.RegistrationDeleteView.as_view()),
    path('registrations/<int:pk>/review/', views.RegistrationReviewView.as_view()),
    path('registrations/<int:pk>/check-in/', views.RegistrationCheckInView.as_view()),
    path('tournaments/<int:pk>/registrations/', views.TournamentRegistrationsView.as_view()),
]
