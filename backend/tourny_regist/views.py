from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from tourny_regist.models import Announcement, Registration, Team, TeamMembership, Tournament
from tourny_regist.permissions import IsApprovedOrganizer, IsPublicOrOwner, IsTournamentStaffOrAdmin
from tourny_regist.serializers import (
    AdminTournamentSerializer,
    AdminTournamentUpdateSerializer,
    AnnouncementCreateSerializer,
    AnnouncementSerializer,
    RegistrationCreateSerializer,
    RegistrationReviewSerializer,
    RegistrationSerializer,
    TeamCreateSerializer,
    TeamJoinSerializer,
    TeamSerializer,
    TournamentApplicationSerializer,
    TournamentDetailSerializer,
    TournamentListSerializer,
    TournamentUpdateSerializer,
)


class TournamentListView(generics.ListCreateAPIView):
    queryset = Tournament.objects.filter(
        status=Tournament.Status.APPROVED, is_published=True,
    ).select_related('game', 'organizer').order_by('starts_at')

    def get_serializer_class(self):
        return TournamentApplicationSerializer if self.request.method == 'POST' else TournamentListSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsApprovedOrganizer()]
        return [permissions.AllowAny()]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        tournament = serializer.save()
        return Response(
            TournamentDetailSerializer(tournament, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class MyTournamentsView(generics.ListAPIView):
    serializer_class = TournamentListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Tournament.objects.filter(
            created_by=self.request.user,
        ).select_related('game', 'organizer').order_by('-created_at')


class TournamentDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Tournament.objects.select_related('game', 'organizer')

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return TournamentUpdateSerializer
        return TournamentDetailSerializer

    def get_permissions(self):
        if self.request.method in ('DELETE', 'PATCH', 'PUT'):
            return [permissions.IsAuthenticated(), IsTournamentStaffOrAdmin()]
        return [IsPublicOrOwner()]

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(TournamentDetailSerializer(self.get_object(), context={'request': request}).data)


class TournamentPublishView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)

        if tournament.status != Tournament.Status.APPROVED:
            raise ValidationError({'detail': 'Only an admin-approved tournament can be published.'})

        tournament.is_published = bool(request.data.get('publish', True))
        tournament.save(update_fields=['is_published'])
        return Response(TournamentDetailSerializer(tournament, context={'request': request}).data)


class TournamentAnnouncementsView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        return AnnouncementCreateSerializer if self.request.method == 'POST' else AnnouncementSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsTournamentStaffOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        return Announcement.objects.filter(tournament_id=self.kwargs['pk']).select_related('author')

    def create(self, request, *args, **kwargs):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(request, tournament)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(tournament=tournament, author=request.user)
        return Response(AnnouncementSerializer(announcement).data, status=status.HTTP_201_CREATED)


class AnnouncementDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def delete(self, request, pk):
        announcement = get_object_or_404(Announcement.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, announcement.tournament)
        announcement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminTournamentListView(generics.ListAPIView):
    serializer_class = AdminTournamentSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Tournament.objects.select_related('game', 'organizer', 'created_by').order_by('-created_at')

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


class AdminTournamentDetailView(generics.RetrieveUpdateAPIView):
    queryset = Tournament.objects.select_related('game', 'organizer', 'created_by')
    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return AdminTournamentUpdateSerializer
        return AdminTournamentSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        return Response(AdminTournamentSerializer(self.get_object(), context={'request': request}).data)


def _user_team_for_tournament(user, tournament):
    membership = TeamMembership.objects.filter(
        player=user, team__tournament=tournament,
    ).select_related('team').first()
    return membership.team if membership else None


class TeamCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk, status=Tournament.Status.APPROVED)
        if tournament.team_size <= 1:
            raise ValidationError({'detail': 'This tournament does not use team registration.'})
        if not tournament.is_registration_open:
            raise ValidationError({'detail': 'Registration is closed for this tournament.'})
        if _user_team_for_tournament(request.user, tournament) is not None:
            raise ValidationError({'detail': 'You are already on a team for this tournament.'})

        serializer = TeamCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = Team.objects.create(tournament=tournament, captain=request.user, **serializer.validated_data)
        TeamMembership.objects.create(team=team, player=request.user)
        return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)


class MyTeamView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        team = _user_team_for_tournament(request.user, tournament)
        if team is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(TeamSerializer(team).data)


class TeamJoinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk, status=Tournament.Status.APPROVED)

        if not tournament.is_registration_open:
            raise ValidationError({'detail': 'Registration is closed for this tournament.'})
        if _user_team_for_tournament(request.user, tournament) is not None:
            raise ValidationError({'detail': 'You are already on a team for this tournament.'})

        serializer = TeamJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['invite_code'].strip().upper()
        team = Team.objects.filter(tournament=tournament, invite_code=code).first()
        if team is None:
            raise ValidationError({'invite_code': 'Invalid invite code.'})
        if team.members.count() >= tournament.team_size:
            raise ValidationError({'detail': 'This team is already full.'})

        TeamMembership.objects.create(team=team, player=request.user)
        return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)


class TeamLeaveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        try:
            team.registration
        except Registration.DoesNotExist:
            pass
        else:
            raise ValidationError({'detail': 'This team is already registered — contact the organizer to make changes.'})

        if team.captain_id == request.user.pk:
            team.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        membership = TeamMembership.objects.filter(team=team, player=request.user).first()
        if membership is None:
            raise PermissionDenied('You are not a member of this team.')
        membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeamRegisterView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        team = get_object_or_404(Team.objects.select_related('tournament'), pk=pk)
        tournament = team.tournament

        if team.captain_id != request.user.pk:
            raise PermissionDenied('Only the team captain can register the team.')
        if team.members.count() != tournament.team_size:
            raise ValidationError({'detail': f'Your roster must have exactly {tournament.team_size} member(s) to register.'})
        if not tournament.is_registration_open:
            raise ValidationError({'detail': 'Registration is closed for this tournament.'})
        if tournament.registration_deadline and timezone.now() > tournament.registration_deadline:
            raise ValidationError({'detail': 'The registration deadline for this tournament has passed.'})
        if Registration.objects.filter(tournament=tournament, player=request.user).exists():
            raise ValidationError({'detail': 'This team is already registered.'})
        if tournament.max_participants is not None and tournament.registrations.count() >= tournament.max_participants:
            raise ValidationError({'detail': 'This tournament has reached its participant limit.'})

        registration = Registration.objects.create(tournament=tournament, player=request.user, team=team)
        return Response(RegistrationSerializer(registration, context={'request': request}).data, status=status.HTTP_201_CREATED)


class RegistrationCreateView(generics.CreateAPIView):
    serializer_class = RegistrationCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        registration = serializer.save()
        return Response(RegistrationSerializer(registration, context={'request': request}).data, status=status.HTTP_201_CREATED)


class RegistrationDeleteView(generics.DestroyAPIView):
    queryset = Registration.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        registration = super().get_object()
        if registration.player_id != self.request.user.pk and not self.request.user.is_staff:
            raise PermissionDenied('You can only cancel your own registration.')
        return registration


class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Registration.objects.filter(player=self.request.user).select_related('tournament', 'player', 'team')


class TournamentRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, tournament)
        return Registration.objects.filter(tournament=tournament).select_related('tournament', 'player', 'team')


class RegistrationReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, registration.tournament)

        serializer = RegistrationReviewSerializer(registration, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(RegistrationSerializer(registration, context={'request': request}).data)


class RegistrationCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, registration.tournament)

        check_in = request.data.get('checked_in', True)
        if isinstance(check_in, str):
            check_in = check_in.strip().lower() not in ('false', '0', '')

        if check_in:
            if registration.checked_in:
                raise ValidationError({'detail': 'This registration is already checked in.'})
            if registration.status == Registration.Status.REJECTED:
                raise ValidationError({'detail': 'A rejected registration cannot be checked in.'})
            if registration.tournament.registration_fee > 0 and registration.status != Registration.Status.APPROVED:
                raise ValidationError({'detail': 'This registration cannot be checked in until its payment is approved.'})
            registration.checked_in = True
            registration.checked_in_at = timezone.now()
        else:
            if not registration.checked_in:
                raise ValidationError({'detail': 'This registration is not checked in.'})
            registration.checked_in = False
            registration.checked_in_at = None

        registration.save(update_fields=['checked_in', 'checked_in_at'])
        return Response(RegistrationSerializer(registration, context={'request': request}).data)
