import csv

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.audit import log_action
from core.models import AdminReviewRequest, AuditLog, Dispute
from core.serializers import DisputeCreateSerializer, DisputeSerializer
from tourny_regist import lifecycle
from tourny_regist.emails import send_announcement_emails
from tourny_regist.models import Announcement, Registration, Team, TeamMembership, Tournament, TournamentRuleVersion
from tourny_regist.permissions import IsApprovedOrganizer, IsPublicOrOwner, IsTournamentStaffOrAdmin
from tourny_regist.serializers import (
    AdminReviewRequestDecideSerializer,
    AdminReviewRequestSerializer,
    AdminTournamentSerializer,
    AdminTournamentUpdateSerializer,
    AnnouncementCreateSerializer,
    AnnouncementSerializer,
    AuditLogSerializer,
    RegistrationCreateSerializer,
    RegistrationReviewSerializer,
    RegistrationSerializer,
    TeamCreateSerializer,
    TeamJoinSerializer,
    TeamSerializer,
    TournamentApplicationSerializer,
    TournamentDetailSerializer,
    TournamentDraftSerializer,
    TournamentListSerializer,
    TournamentRescheduleRequestSerializer,
    TournamentRuleVersionCreateSerializer,
    TournamentRuleVersionSerializer,
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


class TournamentDraftCreateView(generics.CreateAPIView):
    serializer_class = TournamentDraftSerializer
    permission_classes = [permissions.IsAuthenticated, IsApprovedOrganizer]

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


class TournamentSubmitView(APIView):
    """DRAFT -> PENDING. See tourny_regist.lifecycle.submit_tournament for the
    validation this enforces before the tournament reaches admin review."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        tournament = lifecycle.submit_tournament(tournament, request.user)
        return Response(TournamentDetailSerializer(tournament, context={'request': request}).data)


class TournamentResubmitView(APIView):
    """REJECTED -> PENDING, mirroring organizer.views.OrganizerResubmitView."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        tournament = lifecycle.resubmit_tournament(tournament, request.user)
        return Response(TournamentDetailSerializer(tournament, context={'request': request}).data)


class TournamentCancelView(APIView):
    """DRAFT/PENDING/APPROVED -> CANCELLED, immediately if safe (no
    registrations, no bracket) — otherwise files an AdminReviewRequest and
    returns 202 rather than cancelling. See tourny_regist.lifecycle."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        reason = request.data.get('reason', '')
        try:
            tournament = lifecycle.cancel_tournament(tournament, request.user, reason)
        except lifecycle.NeedsAdminReview:
            try:
                with transaction.atomic():
                    AdminReviewRequest.objects.create(
                        requested_by=request.user,
                        request_type=AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION,
                        reason=reason,
                        content_type=ContentType.objects.get_for_model(Tournament),
                        object_id=tournament.pk,
                    )
                log_action(request.user, 'tournament.cancellation_review_requested', tournament, reason=reason)
            except IntegrityError:
                pass  # a pending request for this already exists — nothing new to create, still a 202
            return Response(
                {'detail': 'This tournament has existing registrations or a bracket, so cancellation needs admin review. Your request has been submitted.'},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(TournamentDetailSerializer(tournament, context={'request': request}).data)


class TournamentRescheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        serializer = TournamentRescheduleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tournament = lifecycle.reschedule_tournament(tournament, request.user, **serializer.validated_data)
        return Response(TournamentDetailSerializer(tournament, context={'request': request}).data)


class TournamentDuplicateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        new_tournament = lifecycle.duplicate_tournament(tournament, request.user)
        return Response(
            TournamentDetailSerializer(new_tournament, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class TournamentAnnouncementsView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        return AnnouncementCreateSerializer if self.request.method == 'POST' else AnnouncementSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsTournamentStaffOrAdmin()]
        # Same visibility as the tournament itself (TournamentDetailView) —
        # a client could otherwise list announcements for a draft/pending/
        # unpublished tournament ID it has no relationship to, just by
        # guessing the ID, since this previously only required being
        # authenticated at all (any account), not a stakeholder in *this*
        # tournament.
        return [permissions.IsAuthenticated(), IsPublicOrOwner()]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, tournament)
        return Announcement.objects.filter(tournament=tournament).select_related('author')

    def create(self, request, *args, **kwargs):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(request, tournament)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save(tournament=tournament, author=request.user)
        send_announcement_emails(tournament, announcement)
        return Response(AnnouncementSerializer(announcement).data, status=status.HTTP_201_CREATED)


class AnnouncementDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def delete(self, request, pk):
        announcement = get_object_or_404(Announcement.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, announcement.tournament)
        announcement.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TournamentRulesView(APIView):
    """GET has the same visibility as the tournament itself (IsPublicOrOwner:
    staff, the owning organizer, or anyone at all once the tournament is
    APPROVED+published) — not a blanket AllowAny, which would let any client
    read a draft/pending/unpublished tournament's rules (and, until this was
    fixed, the real email of whoever published them) just by guessing its ID.
    POST (publish a new version) is staff/organizer only and never edits an
    existing TournamentRuleVersion row — see that model's docstring for why
    publishing always appends."""

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsTournamentStaffOrAdmin()]
        return [IsPublicOrOwner()]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        current = tournament.current_rule_version()
        if current is None:
            return Response(None)
        return Response(TournamentRuleVersionSerializer(current).data)

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)

        serializer = TournamentRuleVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        latest = tournament.current_rule_version()
        next_version = (latest.version + 1) if latest else 1
        rules = TournamentRuleVersion.objects.create(
            tournament=tournament, version=next_version, created_by=request.user, **serializer.validated_data,
        )
        log_action(request.user, 'tournament.rules_published', tournament, version=next_version)
        return Response(TournamentRuleVersionSerializer(rules).data, status=status.HTTP_201_CREATED)


class TournamentRulesHistoryView(generics.ListAPIView):
    serializer_class = TournamentRuleVersionSerializer
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, tournament)
        return TournamentRuleVersion.objects.filter(tournament=tournament).select_related('created_by')


class RegistrationAcknowledgeRulesView(APIView):
    """Lets a player who registered before the rules changed (or before any
    were published) explicitly re-acknowledge the current version — the
    counterpart to the automatic stamp RegistrationCreateSerializer.create
    does at registration time. Only the registrant themselves or staff/the
    organizer can do this on their behalf (e.g. a phone check-in)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        is_self = registration.player_id == request.user.pk
        if not is_self and not IsTournamentStaffOrAdmin().has_object_permission(request, self, registration.tournament):
            raise PermissionDenied()

        current = registration.tournament.current_rule_version()
        if current is None:
            raise ValidationError({'detail': 'This tournament has no published rules to acknowledge.'})

        registration.accepted_rules_version = current.version
        registration.save(update_fields=['accepted_rules_version'])
        return Response(RegistrationSerializer(registration, context={'request': request}).data)


class TournamentChampionSeenView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        if tournament.champion_id != request.user.pk:
            raise PermissionDenied('You are not the champion of this tournament.')
        if tournament.champion_seen_at is None:
            tournament.champion_seen_at = timezone.now()
            tournament.save(update_fields=['champion_seen_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TournamentDisputeListCreateView(APIView):
    """GET is staff/organizer only (the full case queue for this tournament).
    POST is open to any stakeholder — staff, the organizer, or anyone with a
    Registration here — since filing a dispute is exactly the self-service
    action a participant needs, not something to gate behind staff status."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        if not IsTournamentStaffOrAdmin().has_object_permission(request, self, tournament):
            raise PermissionDenied()
        disputes = Dispute.objects.filter(
            content_type=ContentType.objects.get_for_model(Tournament), object_id=tournament.pk,
        ).select_related('filed_by', 'resolved_by').prefetch_related('evidence').order_by('-created_at')
        return Response(DisputeSerializer(disputes, many=True, context={'request': request}).data)

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        is_stakeholder = (
            IsTournamentStaffOrAdmin().has_object_permission(request, self, tournament)
            or Registration.objects.filter(tournament=tournament, player=request.user).exists()
        )
        if not is_stakeholder:
            raise PermissionDenied('Only tournament staff or a registered participant may file a dispute.')

        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispute = Dispute.objects.create(
            filed_by=request.user,
            content_type=ContentType.objects.get_for_model(Tournament),
            object_id=tournament.pk,
            description=serializer.validated_data['description'],
        )
        log_action(request.user, 'dispute.filed', tournament)
        return Response(DisputeSerializer(dispute, context={'request': request}).data, status=status.HTTP_201_CREATED)


class TournamentSeedingView(APIView):
    """Manual bracket seeding — see Registration.seed's docstring. Blocked
    entirely once a bracket exists rather than having its own post-bracket
    permission tier: brackets.services.reset_bracket is already the single
    gate for "how do I change something that affects an existing bracket",
    and duplicating that safety logic here would be two places that could
    drift apart."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        registrations = Registration.objects.filter(
            tournament=tournament, checked_in=True,
        ).select_related('player').order_by('seed', 'registered_at')
        return Response(RegistrationSerializer(registrations, many=True, context={'request': request}).data)

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        if hasattr(tournament, 'bracket'):
            raise ValidationError({'detail': 'Reset the bracket before changing seeding.'})

        seeds = request.data.get('seeds')
        if not isinstance(seeds, list):
            raise ValidationError({'seeds': 'Expected a list of {registration_id, seed}.'})

        with transaction.atomic():
            for entry in seeds:
                reg_id = entry.get('registration_id')
                seed_value = entry.get('seed')
                updated = Registration.objects.filter(tournament=tournament, pk=reg_id).update(seed=seed_value)
                if not updated:
                    raise ValidationError({'detail': f'Registration {reg_id} was not found in this tournament.'})

        log_action(request.user, 'tournament.reseeded', tournament)
        registrations = Registration.objects.filter(
            tournament=tournament, checked_in=True,
        ).select_related('player').order_by('seed', 'registered_at')
        return Response(RegistrationSerializer(registrations, many=True, context={'request': request}).data)


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


class AdminReviewRequestListView(generics.ListAPIView):
    serializer_class = AdminReviewRequestSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = AdminReviewRequest.objects.select_related('requested_by', 'decided_by').order_by('-created_at')

    def get_queryset(self):
        queryset = super().get_queryset()
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


class AdminReviewRequestDecideView(APIView):
    """Approving does not generically replay the requester's action — each
    request_type is dispatched explicitly to the same service function its
    safe self-service path would have called, per
    core.models.AdminReviewRequest's docstring."""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        with transaction.atomic():
            review_request = get_object_or_404(
                AdminReviewRequest.objects.select_for_update(), pk=pk,
            )
            if review_request.status != AdminReviewRequest.Status.PENDING:
                raise ValidationError({'detail': 'This request has already been decided.'})

            serializer = AdminReviewRequestDecideSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            new_status = serializer.validated_data['status']
            decision_reason = serializer.validated_data.get('reason', '')

            if new_status == AdminReviewRequest.Status.APPROVED:
                if review_request.request_type == AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION:
                    lifecycle.cancel_tournament(
                        review_request.target, request.user, review_request.reason, bypass_safety_check=True,
                    )
                elif review_request.request_type == AdminReviewRequest.RequestType.REGISTRATION_CANCELLATION:
                    lifecycle.cancel_registration(
                        review_request.target, request.user, review_request.reason, bypass_safety_check=True,
                    )
                elif review_request.request_type == AdminReviewRequest.RequestType.BRACKET_RESET:
                    # Local import: brackets depends on tourny_regist, not the
                    # reverse, everywhere else — this dispatcher is the one
                    # place that needs to reach the other way, so it's kept
                    # to a function-local import rather than a module-level
                    # one that would make the dependency look bidirectional.
                    from brackets.services import reset_bracket
                    reset_bracket(review_request.target, request.user, review_request.reason, bypass_safety_check=True)
                else:
                    raise ValidationError({'detail': f'Unhandled request_type: {review_request.request_type}'})

            review_request.status = new_status
            review_request.decided_by = request.user
            review_request.decision_reason = decision_reason
            review_request.decided_at = timezone.now()
            review_request.save(update_fields=['status', 'decided_by', 'decision_reason', 'decided_at'])
            log_action(
                request.user, f'admin_review_request.{new_status}', review_request, reason=decision_reason,
            )

        return Response(AdminReviewRequestSerializer(review_request).data)


def _user_team_for_tournament(user, tournament):
    membership = TeamMembership.objects.filter(
        player=user, team__tournament=tournament,
    ).select_related('team').first()
    return membership.team if membership else None


class TeamCreateView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.IsAuthenticated(), IsTournamentStaffOrAdmin()]
        return [permissions.IsAuthenticated()]

    def get(self, request, pk):
        """Organizer/staff roster overview — every team in the tournament,
        not just the requester's own (that's MyTeamView)."""
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        teams = Team.objects.filter(tournament=tournament).select_related('captain').prefetch_related('members__player')
        return Response(TeamSerializer(teams, many=True).data)

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk, status=Tournament.Status.APPROVED)
        if tournament.team_size <= 1:
            raise ValidationError({'detail': 'This tournament does not use team registration.'})
        if not tournament.is_registration_open:
            raise ValidationError({'detail': 'Registration is closed for this tournament.'})

        serializer = TeamCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                # Locks the tournament row — not just the team being created,
                # which doesn't exist yet to lock — so this can't race with a
                # simultaneous TeamJoinView call for the *same player* against
                # a different team in this tournament. Each view previously
                # only locked its own team's row, which doesn't serialize
                # against the other: a player could create team A here and
                # join team B via TeamJoinView at the same instant, since
                # neither request's "already on a team" check would see the
                # other's not-yet-committed membership. Re-checking inside
                # the lock (not just before it) is what actually closes that.
                Tournament.objects.select_for_update().filter(pk=tournament.pk).first()
                if _user_team_for_tournament(request.user, tournament) is not None:
                    raise ValidationError({'detail': 'You are already on a team for this tournament.'})
                team = Team.objects.create(tournament=tournament, captain=request.user, **serializer.validated_data)
                TeamMembership.objects.create(team=team, player=request.user)
        except IntegrityError:
            raise ValidationError({'name': 'A team with this name already exists in this tournament.'})
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
    throttle_scope = 'team_join'

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk, status=Tournament.Status.APPROVED)

        if not tournament.is_registration_open:
            raise ValidationError({'detail': 'Registration is closed for this tournament.'})

        serializer = TeamJoinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['invite_code'].strip().upper()

        # Locks the tournament row, not just the target team's — the same
        # broadened lock as TeamCreateView, and for the identical reason: a
        # lock scoped to only the team being joined doesn't serialize
        # against a simultaneous join/create against a *different* team by
        # the same player. "Already on a team" is re-checked inside the
        # lock, not just before it, so the two requests can't both pass it
        # before either commits.
        with transaction.atomic():
            Tournament.objects.select_for_update().filter(pk=tournament.pk).first()
            if _user_team_for_tournament(request.user, tournament) is not None:
                raise ValidationError({'detail': 'You are already on a team for this tournament.'})
            team = Team.objects.filter(tournament=tournament, invite_code=code).first()
            if team is None:
                raise ValidationError({'invite_code': 'Invalid invite code.'})
            if team.is_locked:
                raise ValidationError({'detail': 'This team\'s roster is locked and cannot accept new members.'})
            if team.members.count() >= tournament.team_size:
                raise ValidationError({'detail': 'This team is already full.'})
            try:
                TeamMembership.objects.create(team=team, player=request.user)
            except IntegrityError:
                raise ValidationError({'detail': 'You are already on this team.'})

        return Response(TeamSerializer(team).data, status=status.HTTP_201_CREATED)


class TeamLeaveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        if team.is_locked:
            raise ValidationError({'detail': 'This team\'s roster is locked — contact the organizer to make changes.'})
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
        if tournament.status != Tournament.Status.APPROVED:
            raise ValidationError({'detail': 'This tournament is not open for registration.'})
        if team.members.count() != tournament.team_size:
            raise ValidationError({'detail': f'Your roster must have exactly {tournament.team_size} member(s) to register.'})
        if not tournament.is_registration_open:
            raise ValidationError({'detail': 'Registration is closed for this tournament.'})
        if tournament.registration_deadline and timezone.now() > tournament.registration_deadline:
            raise ValidationError({'detail': 'The registration deadline for this tournament has passed.'})

        try:
            # Locks the tournament row so a simultaneous registration can't slip
            # past the max_participants check between here and the create() below.
            with transaction.atomic():
                Tournament.objects.select_for_update().get(pk=tournament.pk)
                if Registration.objects.filter(tournament=tournament, player=request.user).exists():
                    raise ValidationError({'detail': 'This team is already registered.'})
                if tournament.max_participants is not None and tournament.registrations.count() >= tournament.max_participants:
                    raise ValidationError({'detail': 'This tournament has reached its participant limit.'})
                registration = Registration.objects.create(tournament=tournament, player=request.user, team=team)
        except IntegrityError:
            raise ValidationError({'detail': 'This team is already registered.'})

        return Response(RegistrationSerializer(registration, context={'request': request}).data, status=status.HTTP_201_CREATED)


class TeamLockView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        team = get_object_or_404(Team.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, team.tournament)
        team = lifecycle.lock_team_roster(team, request.user)
        return Response(TeamSerializer(team).data)


class TeamUnlockView(APIView):
    # Staff only, not IsTournamentStaffOrAdmin's organizer branch — re-opening
    # a locked roster is the "exceptional workflow" spec section 12 asks for.
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        team = get_object_or_404(Team, pk=pk)
        team = lifecycle.unlock_team_roster(team, request.user)
        return Response(TeamSerializer(team).data)


class TeamSubstituteView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        team = get_object_or_404(Team.objects.select_related('tournament'), pk=pk)
        outgoing_id = request.data.get('outgoing_player_id')
        incoming_id = request.data.get('incoming_player_id')
        reason = request.data.get('reason', '')
        if not outgoing_id or not incoming_id:
            raise ValidationError({'detail': 'outgoing_player_id and incoming_player_id are both required.'})

        User = get_user_model()
        outgoing_player = get_object_or_404(User, pk=outgoing_id)
        incoming_player = get_object_or_404(User, pk=incoming_id)
        team = lifecycle.substitute_team_member(team, request.user, outgoing_player, incoming_player, reason)
        return Response(TeamSerializer(team).data)


class TeamHistoryView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get_queryset(self):
        team = get_object_or_404(Team.objects.select_related('tournament'), pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, team.tournament)
        return AuditLog.objects.filter(
            content_type=ContentType.objects.get_for_model(Team), object_id=team.pk,
        ).select_related('actor').order_by('-created_at')


class RegistrationDisqualifyView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, registration.tournament)
        registration = lifecycle.disqualify_registration(registration, request.user, request.data.get('reason', ''))
        return Response(RegistrationSerializer(registration, context={'request': request}).data)


class RegistrationCreateView(generics.CreateAPIView):
    serializer_class = RegistrationCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Locks the tournament row (if the request names one at all — an
        # invalid/missing value is left for the serializer's own validation
        # to reject) so two simultaneous registrations near the last open
        # slot serialize instead of both reading "count < max_participants"
        # and both succeeding — mirrors TeamJoinView's select_for_update on
        # the Team row for the equivalent race there. The (tournament,
        # player) duplicate-registration case has its own backstop
        # independent of this lock: Registration.Meta's unique_together.
        with transaction.atomic():
            tournament_id = request.data.get('tournament')
            if tournament_id:
                Tournament.objects.select_for_update().filter(pk=tournament_id).first()
            serializer = self.get_serializer(data=request.data, context={'request': request})
            serializer.is_valid(raise_exception=True)
            registration = serializer.save()
        return Response(RegistrationSerializer(registration, context={'request': request}).data, status=status.HTTP_201_CREATED)


class RegistrationDeleteView(generics.DestroyAPIView):
    """A player's own early self-withdrawal — a hard delete, distinct from
    lifecycle.cancel_registration's soft-cancel (see that function's
    docstring). Only "early" as of the tournament having no bracket yet:
    once one exists, this player may already be seeded into a live match
    (READY, or even COMPLETED and advanced), and a hard delete here would
    silently orphan it — the opponent left waiting for someone whose
    Registration row no longer exists, with no forfeit recorded and no way
    for the organizer to see why. Past that point, withdrawal has to go
    through lifecycle.disqualify_registration or cancel_registration, both
    of which know how to unwind a live match cleanly."""

    queryset = Registration.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        registration = super().get_object()
        if registration.player_id != self.request.user.pk and not self.request.user.is_staff:
            raise PermissionDenied('You can only cancel your own registration.')
        return registration

    def perform_destroy(self, instance):
        if hasattr(instance.tournament, 'bracket'):
            raise ValidationError({
                'detail': (
                    'This tournament already has a bracket, so withdrawing directly could leave a live '
                    'match without an opponent. Contact the organizer to cancel your registration instead.'
                ),
            })
        instance.delete()


class MyRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Registration.objects.filter(player=self.request.user).select_related('tournament', 'player', 'team')


def _filter_registrations(queryset, request):
    search = request.query_params.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(full_name__icontains=search) | Q(gaming_username__icontains=search)
            | Q(contact_email__icontains=search) | Q(player__email__icontains=search),
        )
    status_param = request.query_params.get('status')
    if status_param:
        queryset = queryset.filter(status=status_param)
    checked_in_param = request.query_params.get('checked_in')
    if checked_in_param is not None:
        queryset = queryset.filter(checked_in=checked_in_param.strip().lower() in ('true', '1'))
    return queryset


class TournamentRegistrationsView(generics.ListAPIView):
    serializer_class = RegistrationSerializer
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, tournament)
        queryset = Registration.objects.filter(tournament=tournament).select_related('tournament', 'player', 'team')
        return _filter_registrations(queryset, self.request)


class RegistrationExportView(APIView):
    """CSV export of a tournament's registrations, respecting the same
    search/status/checked_in filters as TournamentRegistrationsView."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        queryset = _filter_registrations(
            Registration.objects.filter(tournament=tournament).select_related('player', 'team'),
            request,
        )

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{tournament.name}-registrations.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'Full Name', 'Gaming Username', 'Email', 'Player Account Email', 'Team', 'Status',
            'Checked In', 'Registered At',
        ])
        for r in queryset:
            writer.writerow([
                r.full_name, r.gaming_username, r.contact_email, r.player.email,
                r.team.name if r.team_id else '', r.status, r.checked_in, r.registered_at,
            ])
        return response


class RegistrationHistoryView(generics.ListAPIView):
    """Audit trail for one registration — approvals/rejections/check-ins/
    cancellations. Scoped per-registration (not a generic audit-log browser)
    so this can't be used to enumerate audit entries for objects the
    requester doesn't manage."""
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get_queryset(self):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=self.kwargs['pk'])
        self.check_object_permissions(self.request, registration.tournament)
        return AuditLog.objects.filter(
            content_type=ContentType.objects.get_for_model(Registration), object_id=registration.pk,
        ).select_related('actor').order_by('-created_at')


class RegistrationReviewView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, registration.tournament)

        serializer = RegistrationReviewSerializer(registration, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(
            request.user, f'registration.{registration.status}', registration,
            reason=registration.rejection_reason,
        )
        return Response(RegistrationSerializer(registration, context={'request': request}).data)


class RegistrationCancelView(APIView):
    """APPROVED/PENDING -> CANCELLED, immediately if safe — otherwise files an
    AdminReviewRequest and returns 202, same shape as TournamentCancelView."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament', 'player'), pk=pk)
        self.check_object_permissions(request, registration.tournament)
        reason = request.data.get('reason', '')
        try:
            registration = lifecycle.cancel_registration(registration, request.user, reason)
        except lifecycle.NeedsAdminReview:
            try:
                with transaction.atomic():
                    AdminReviewRequest.objects.create(
                        requested_by=request.user,
                        request_type=AdminReviewRequest.RequestType.REGISTRATION_CANCELLATION,
                        reason=reason,
                        content_type=ContentType.objects.get_for_model(Registration),
                        object_id=registration.pk,
                    )
                log_action(request.user, 'registration.cancellation_review_requested', registration, reason=reason)
            except IntegrityError:
                pass  # a pending request for this already exists — nothing new to create, still a 202
            return Response(
                {'detail': 'This participant has already played a match, so cancellation needs admin review. Your request has been submitted.'},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(RegistrationSerializer(registration, context={'request': request}).data)


class RegistrationCheckInView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        registration = get_object_or_404(Registration.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, registration.tournament)

        # Once a bracket exists, the checked-in set at generation time is
        # what eligible_participants()/seed_players() (brackets/services.py)
        # were built from — and standings()/generate_next_swiss_round()
        # re-derive *live* from whatever is currently checked_in, not a
        # roster frozen at generation time. Toggling check-in after the fact
        # either injects someone who never played earlier rounds into a
        # later one, or silently drops someone with a completed result and
        # no forfeit recorded. lifecycle.disqualify_registration is the
        # correct way to remove a bracket-era participant — it forfeits
        # their live match as part of the same transaction.
        if hasattr(registration.tournament, 'bracket'):
            raise ValidationError({
                'detail': (
                    'This tournament already has a bracket — check-in status can no longer be changed here. '
                    'Use disqualification to remove a participant.'
                ),
            })

        check_in = request.data.get('checked_in', True)
        if isinstance(check_in, str):
            check_in = check_in.strip().lower() not in ('false', '0', '')

        if check_in:
            if registration.checked_in:
                raise ValidationError({'detail': 'This registration is already checked in.'})
            # These three are terminal/negative statuses regardless of
            # whether the tournament charges a fee — REJECTED was already
            # guarded; DISQUALIFIED/CANCELLED previously weren't, so a
            # disqualified player (already forfeited out of their bracket
            # match) could be checked back in on any free tournament (the
            # registration_fee > 0 gate below never even runs for one),
            # re-entering eligible_participants()/seed_players() as if
            # nothing had happened.
            if registration.status in (
                Registration.Status.REJECTED, Registration.Status.DISQUALIFIED, Registration.Status.CANCELLED,
            ):
                raise ValidationError({'detail': f'A {registration.status} registration cannot be checked in.'})
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
        log_action(request.user, 'registration.checked_in' if check_in else 'registration.checked_out', registration)
        return Response(RegistrationSerializer(registration, context={'request': request}).data)
