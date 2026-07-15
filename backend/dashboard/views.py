from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from brackets.models import Match
from core.models import Follow
from games.models import Game
from notifications.models import Notification
from organizer.models import Organizer
from partners.models import Partner
from tourny_regist.models import Registration, Tournament

User = get_user_model()


class PlayerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        registrations = Registration.objects.filter(player=user).select_related('tournament')
        upcoming_registrations = registrations.filter(tournament__starts_at__gt=timezone.now())
        upcoming_matches = Match.objects.filter(
            Q(player1=user) | Q(player2=user), status=Match.Status.READY,
        ).select_related('tournament', 'player1', 'player2')
        organizer_profile = getattr(user, 'organizer_profile', None)

        return Response({
            'profile': {
                'id': user.pk,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'followers_count': Follow.objects.filter(following=user).count(),
            'following_count': Follow.objects.filter(follower=user).count(),
            'registrations_count': registrations.count(),
            'upcoming_tournaments_count': upcoming_registrations.count(),
            'unread_notifications_count': Notification.objects.filter(recipient=user, is_read=False).count(),
            'upcoming_matches': [
                {
                    'id': match.pk,
                    'tournament': match.tournament.name,
                    'round_number': match.round_number,
                    'opponent_email': (
                        match.player2.email if match.player1_id == user.pk else match.player1.email
                    ),
                }
                for match in upcoming_matches
            ],
            'is_organizer': organizer_profile is not None,
            'organizer_status': organizer_profile.status if organizer_profile else None,
        })


class OrganizerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        organizer = getattr(request.user, 'organizer_profile', None)
        if organizer is None:
            raise NotFound({'detail': 'You have not registered as an organizer yet.'})

        tournaments = Tournament.objects.filter(organizer=organizer)
        tournament_ids = list(tournaments.values_list('id', flat=True))

        return Response({
            'organizer': {
                'company_name': organizer.company_name,
                'status': organizer.status,
            },
            'tournaments_count': tournaments.count(),
            'active_tournaments_count': tournaments.filter(is_registration_open=True).count(),
            'total_registrations': Registration.objects.filter(tournament_id__in=tournament_ids).count(),
            'matches_awaiting_result': Match.objects.filter(
                tournament_id__in=tournament_ids, status=Match.Status.READY,
            ).count(),
            'tournaments': [
                {
                    'id': tournament.pk,
                    'name': tournament.name,
                    'starts_at': tournament.starts_at,
                    'is_registration_open': tournament.is_registration_open,
                    'registrations_count': Registration.objects.filter(tournament=tournament).count(),
                }
                for tournament in tournaments.order_by('-starts_at')[:10]
            ],
        })


class AdminDashboardView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        return Response({
            'total_users': User.objects.count(),
            'total_organizers': Organizer.objects.count(),
            'organizers_by_status': {
                choice_value: Organizer.objects.filter(status=choice_value).count()
                for choice_value, _ in Organizer.Status.choices
            },
            'total_games': Game.objects.count(),
            'total_tournaments': Tournament.objects.count(),
            'total_registrations': Registration.objects.count(),
            'total_partners': Partner.objects.count(),
        })


class PlatformStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            'total_players': User.objects.count(),
            'total_organizers': Organizer.objects.filter(status=Organizer.Status.APPROVED).count(),
            'total_games': Game.objects.filter(is_active=True).count(),
            'total_tournaments': Tournament.objects.count(),
            'total_partners': Partner.objects.filter(is_active=True).count(),
            'total_matches_played': Match.objects.filter(status=Match.Status.COMPLETED).count(),
        })
