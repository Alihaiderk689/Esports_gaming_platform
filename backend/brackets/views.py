from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from brackets.models import Bracket, Match
from brackets.permissions import IsPublicOrTournamentStakeholder
from brackets.serializers import (
    BracketSerializer,
    MatchForfeitSerializer,
    MatchNotesSerializer,
    MatchOverrideSerializer,
    MatchResultSerializer,
    MatchScheduleSerializer,
    MatchSerializer,
)
from brackets.services import (
    NeedsAdminReview,
    complete_match,
    finalize_tournament_champion,
    forfeit_match,
    generate_bracket,
    generate_double_elimination_bracket,
    generate_group_playoff_bracket,
    generate_group_playoff_bracket_phase2,
    generate_next_swiss_round,
    generate_round_robin_bracket,
    generate_swiss_bracket,
    generate_three_game_guarantee_bracket,
    override_match_result,
    preview_bracket,
    reset_bracket,
)
from core.audit import log_action
from core.models import AdminReviewRequest, Dispute
from core.serializers import DisputeCreateSerializer, DisputeSerializer
from tourny_regist.models import Tournament
from tourny_regist.permissions import IsTournamentStaffOrAdmin

_GENERATORS = {
    Bracket.Format.SINGLE: generate_bracket,
    Bracket.Format.DOUBLE: generate_double_elimination_bracket,
    Bracket.Format.GUARANTEE3: generate_three_game_guarantee_bracket,
    Bracket.Format.ROUND_ROBIN: generate_round_robin_bracket,
    Bracket.Format.SWISS: generate_swiss_bracket,
}


class TournamentBracketView(APIView):
    # GET (spectator read) and POST (generation) intentionally use different
    # object-level rules — see get_permissions().
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [permissions.IsAuthenticated(), IsPublicOrTournamentStakeholder()]
        return [permissions.IsAuthenticated(), IsTournamentStaffOrAdmin()]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        bracket = getattr(tournament, 'bracket', None)
        if bracket is None:
            raise NotFound({'detail': 'Bracket has not been generated yet.'})
        return Response(BracketSerializer(bracket).data)

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)

        if Bracket.objects.filter(tournament=tournament).exists():
            raise ValidationError({'detail': 'Bracket has already been generated for this tournament.'})
        if tournament.registrations.filter(checked_in=True).count() < 2:
            raise ValidationError({
                'detail': 'At least 2 checked-in players are required to generate a bracket.',
            })

        bracket_format = request.data.get('format', Bracket.Format.SINGLE)

        if bracket_format == Bracket.Format.GROUP_PLAYOFF:
            bracket = generate_group_playoff_bracket(tournament, num_groups=request.data.get('num_groups'))
        else:
            generator = _GENERATORS.get(bracket_format)
            if generator is None:
                raise ValidationError({'format': f'Unknown bracket format "{bracket_format}".'})
            bracket = generator(tournament)

        tournament.is_registration_open = False
        tournament.save(update_fields=['is_registration_open'])
        return Response(BracketSerializer(bracket).data, status=status.HTTP_201_CREATED)


class TournamentBracketPreviewView(APIView):
    """Read-only — see brackets.services.preview_bracket. Organizer reviews
    seeding/matchups/byes before actually generating (spec: "Generate ->
    Preview -> Organizer confirmation -> Activate")."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        # Deliberately NOT named "format" — that query param name is reserved
        # by DRF's content-negotiation override (URL_FORMAT_OVERRIDE) and gets
        # intercepted before this view ever runs, raising Http404 for any
        # value that isn't a registered renderer format ('json', 'api', ...).
        bracket_format = request.query_params.get('bracket_format', tournament.bracket_format)
        return Response(preview_bracket(tournament, bracket_format))


class TournamentBracketResetView(APIView):
    """Immediate if safe (see brackets.services.reset_bracket) — otherwise
    files an AdminReviewRequest and returns 202, same shape as
    TournamentCancelView/RegistrationCancelView."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        reason = request.data.get('reason', '')
        try:
            reset_bracket(tournament, request.user, reason)
        except NeedsAdminReview:
            try:
                with transaction.atomic():
                    AdminReviewRequest.objects.create(
                        requested_by=request.user,
                        request_type=AdminReviewRequest.RequestType.BRACKET_RESET,
                        reason=reason,
                        content_type=ContentType.objects.get_for_model(Tournament),
                        object_id=tournament.pk,
                    )
                log_action(request.user, 'bracket.reset_review_requested', tournament, reason=reason)
            except IntegrityError:
                pass  # a pending request for this already exists — nothing new to create, still a 202
            return Response(
                {'detail': 'This bracket already has recorded results, so resetting it needs admin review. Your request has been submitted.'},
                status=status.HTTP_202_ACCEPTED,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class TournamentMatchesView(generics.ListAPIView):
    serializer_class = MatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsPublicOrTournamentStakeholder]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        # check_object_permissions() isn't called automatically for a list
        # view the way it is for a single-object view — call it explicitly
        # against the parent tournament (same pattern as
        # TournamentAnnouncementsView, see docs/SECURITY.md's IDOR audit).
        self.check_object_permissions(self.request, tournament)
        return Match.objects.filter(tournament=tournament).select_related('player1', 'player2', 'winner')


class MatchDetailView(generics.RetrieveAPIView):
    queryset = Match.objects.select_related('player1', 'player2', 'winner', 'tournament')
    serializer_class = MatchSerializer
    permission_classes = [permissions.IsAuthenticated, IsPublicOrTournamentStakeholder]

    def get_object(self):
        # GenericAPIView.get_object() would call check_object_permissions()
        # against the Match itself — this view's object-level rule is keyed
        # on the match's Tournament instead (mirrors MatchResultView.patch's
        # self.check_object_permissions(request, match.tournament)), so the
        # lookup is replicated here rather than delegated to super(), which
        # would run the permission check against the wrong object.
        queryset = self.filter_queryset(self.get_queryset())
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        filter_kwargs = {self.lookup_field: self.kwargs[lookup_url_kwarg]}
        match = get_object_or_404(queryset, **filter_kwargs)
        self.check_object_permissions(self.request, match.tournament)
        return match


class MatchResultView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        match = get_object_or_404(
            Match.objects.select_related('tournament', 'player1', 'player2'), pk=pk,
        )
        self.check_object_permissions(request, match.tournament)

        if match.status != Match.Status.READY:
            raise ValidationError({
                'detail': 'This match is not ready for a result (players not yet determined, or already completed).',
            })
        if match.player1_id is None or match.player2_id is None:
            # A one-sided slot is a bye: it is auto-completed at generation time and
            # has no result to report. Reachable only if a bye were somehow left READY,
            # but reporting a "result" for an unplayed game must never be accepted.
            raise ValidationError({'detail': 'A bye advances automatically and has no result to submit.'})

        serializer = MatchResultSerializer(data=request.data, context={'match': match})
        serializer.is_valid(raise_exception=True)

        winner_id = serializer.validated_data['winner']
        winner = match.player1 if match.player1_id == winner_id else match.player2
        complete_match(match, winner, serializer.validated_data.get('score', ''))
        finalize_tournament_champion(match.tournament)

        return Response(MatchSerializer(match).data)


class MatchOverrideView(APIView):
    """Corrects an already-completed match's recorded result. See
    brackets.services.override_match_result for exactly when this is safe —
    it refuses outright (ValidationError, not a silent partial fix) once
    anything downstream has a recorded result of its own."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        match = get_object_or_404(
            Match.objects.select_related('tournament', 'player1', 'player2'), pk=pk,
        )
        self.check_object_permissions(request, match.tournament)

        serializer = MatchOverrideSerializer(data=request.data, context={'match': match})
        serializer.is_valid(raise_exception=True)

        winner_id = serializer.validated_data['winner']
        winner = match.player1 if match.player1_id == winner_id else match.player2
        override_match_result(
            match, request.user, winner,
            serializer.validated_data.get('score', ''), serializer.validated_data['reason'],
        )
        return Response(MatchSerializer(match).data)


class MatchForfeitView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        match = get_object_or_404(
            Match.objects.select_related('tournament', 'player1', 'player2'), pk=pk,
        )
        self.check_object_permissions(request, match.tournament)

        serializer = MatchForfeitSerializer(data=request.data, context={'match': match})
        serializer.is_valid(raise_exception=True)

        forfeiting_id = serializer.validated_data['forfeiting_player']
        forfeiting_player = match.player1 if match.player1_id == forfeiting_id else match.player2
        forfeit_match(match, request.user, forfeiting_player, serializer.validated_data['reason'])
        return Response(MatchSerializer(match).data)


class MatchScheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def patch(self, request, pk):
        match = get_object_or_404(Match.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, match.tournament)

        serializer = MatchScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        match.scheduled_at = serializer.validated_data['scheduled_at']
        match.save(update_fields=['scheduled_at'])
        log_action(request.user, 'match.scheduled', match.tournament, scheduled_at=str(match.scheduled_at), match_id=match.pk)
        return Response(MatchSerializer(match).data)


class MatchNotesView(APIView):
    """Organizer-private notes — deliberately its own endpoint rather than a field
    on MatchSerializer; see that serializer's comment for why."""
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get(self, request, pk):
        match = get_object_or_404(Match.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, match.tournament)
        return Response({'organizer_notes': match.organizer_notes})

    def patch(self, request, pk):
        match = get_object_or_404(Match.objects.select_related('tournament'), pk=pk)
        self.check_object_permissions(request, match.tournament)

        serializer = MatchNotesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        match.organizer_notes = serializer.validated_data['organizer_notes']
        match.save(update_fields=['organizer_notes'])
        return Response({'organizer_notes': match.organizer_notes})


class MatchDisputeCreateView(APIView):
    """Filing a dispute about a specific match — open to either player in it, in
    addition to staff/organizer. See core.models.Dispute for how this and
    TournamentDisputeListCreateView (tourny_regist.views) both feed the same
    generic Dispute model without either app importing the other."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        match = get_object_or_404(Match.objects.select_related('tournament'), pk=pk)
        is_stakeholder = (
            IsTournamentStaffOrAdmin().has_object_permission(request, self, match.tournament)
            or request.user.pk in (match.player1_id, match.player2_id)
        )
        if not is_stakeholder:
            raise PermissionDenied('Only tournament staff or a player in this match may file a dispute.')

        serializer = DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispute = Dispute.objects.create(
            filed_by=request.user,
            content_type=ContentType.objects.get_for_model(Match),
            object_id=match.pk,
            description=serializer.validated_data['description'],
        )
        log_action(request.user, 'dispute.filed', match.tournament, match_id=match.pk)
        return Response(DisputeSerializer(dispute, context={'request': request}).data, status=status.HTTP_201_CREATED)


class TournamentNextRoundView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        bracket = getattr(tournament, 'bracket', None)
        if bracket is None:
            raise NotFound({'detail': 'Bracket has not been generated yet.'})

        generate_next_swiss_round(bracket)
        return Response(BracketSerializer(bracket).data)


class TournamentGeneratePlayoffView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)
        bracket = getattr(tournament, 'bracket', None)
        if bracket is None:
            raise NotFound({'detail': 'Bracket has not been generated yet.'})

        generate_group_playoff_bracket_phase2(bracket)
        return Response(BracketSerializer(bracket).data)
