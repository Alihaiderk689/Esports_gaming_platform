from django.urls import path

from tourny_regist import views

urlpatterns = [
    path('tournaments/', views.TournamentListView.as_view()),
    path('tournaments/mine/', views.MyTournamentsView.as_view()),
    path('tournaments/drafts/', views.TournamentDraftCreateView.as_view()),
    path('tournaments/<int:pk>/', views.TournamentDetailView.as_view()),
    path('tournaments/<int:pk>/publish/', views.TournamentPublishView.as_view()),
    path('tournaments/<int:pk>/submit/', views.TournamentSubmitView.as_view()),
    path('tournaments/<int:pk>/resubmit/', views.TournamentResubmitView.as_view()),
    path('tournaments/<int:pk>/cancel/', views.TournamentCancelView.as_view()),
    path('tournaments/<int:pk>/reschedule/', views.TournamentRescheduleView.as_view()),
    path('tournaments/<int:pk>/duplicate/', views.TournamentDuplicateView.as_view()),
    path('tournaments/<int:pk>/announcements/', views.TournamentAnnouncementsView.as_view()),
    path('announcements/<int:pk>/', views.AnnouncementDeleteView.as_view()),
    path('tournaments/<int:pk>/champion-seen/', views.TournamentChampionSeenView.as_view()),

    path('admin/tournaments/', views.AdminTournamentListView.as_view()),
    path('admin/tournaments/<int:pk>/', views.AdminTournamentDetailView.as_view()),
    path('admin/review-requests/', views.AdminReviewRequestListView.as_view()),
    path('admin/review-requests/<int:pk>/decide/', views.AdminReviewRequestDecideView.as_view()),

    path('tournaments/<int:pk>/teams/', views.TeamCreateView.as_view()),
    path('tournaments/<int:pk>/teams/mine/', views.MyTeamView.as_view()),
    path('tournaments/<int:pk>/teams/join/', views.TeamJoinView.as_view()),
    path('teams/<int:pk>/leave/', views.TeamLeaveView.as_view()),
    path('teams/<int:pk>/register/', views.TeamRegisterView.as_view()),
    path('teams/<int:pk>/lock/', views.TeamLockView.as_view()),
    path('teams/<int:pk>/unlock/', views.TeamUnlockView.as_view()),
    path('teams/<int:pk>/substitute/', views.TeamSubstituteView.as_view()),
    path('teams/<int:pk>/history/', views.TeamHistoryView.as_view()),

    path('registrations/', views.RegistrationCreateView.as_view()),
    path('registrations/me/', views.MyRegistrationsView.as_view()),
    path('registrations/<int:pk>/', views.RegistrationDeleteView.as_view()),
    path('registrations/<int:pk>/review/', views.RegistrationReviewView.as_view()),
    path('registrations/<int:pk>/check-in/', views.RegistrationCheckInView.as_view()),
    path('registrations/<int:pk>/cancel/', views.RegistrationCancelView.as_view()),
    path('registrations/<int:pk>/disqualify/', views.RegistrationDisqualifyView.as_view()),
    path('registrations/<int:pk>/history/', views.RegistrationHistoryView.as_view()),
    path('tournaments/<int:pk>/registrations/', views.TournamentRegistrationsView.as_view()),
    path('tournaments/<int:pk>/registrations/export/', views.RegistrationExportView.as_view()),
    path('tournaments/<int:pk>/seeding/', views.TournamentSeedingView.as_view()),
    path('tournaments/<int:pk>/disputes/', views.TournamentDisputeListCreateView.as_view()),

    path('tournaments/<int:pk>/rules/', views.TournamentRulesView.as_view()),
    path('tournaments/<int:pk>/rules/history/', views.TournamentRulesHistoryView.as_view()),
    path('registrations/<int:pk>/acknowledge-rules/', views.RegistrationAcknowledgeRulesView.as_view()),
]
