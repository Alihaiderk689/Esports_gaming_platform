from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from brackets.models import Bracket, Match
from brackets.serializers import BracketSerializer, MatchResultSerializer, MatchSerializer
from brackets.services import complete_match, generate_bracket
from tourny_regist.models import Tournament
from tourny_regist.permissions import IsTournamentStaffOrAdmin


class TournamentBracketView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsTournamentStaffOrAdmin]

    def get(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        bracket = getattr(tournament, 'bracket', None)
        if bracket is None:
            raise NotFound({'detail': 'Bracket has not been generated yet.'})
        return Response(BracketSerializer(bracket).data)

    def post(self, request, pk):
        tournament = get_object_or_404(Tournament, pk=pk)
        self.check_object_permissions(request, tournament)

        if Bracket.objects.filter(tournament=tournament).exists():
            raise ValidationError({'detail': 'Bracket has already been generated for this tournament.'})
        if tournament.registrations.count() < 2:
            raise ValidationError({'detail': 'At least 2 registered players are required to generate a bracket.'})

        bracket = generate_bracket(tournament)
        tournament.is_registration_open = False
        tournament.save(update_fields=['is_registration_open'])
        return Response(BracketSerializer(bracket).data, status=status.HTTP_201_CREATED)


class TournamentMatchesView(generics.ListAPIView):
    serializer_class = MatchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        tournament = get_object_or_404(Tournament, pk=self.kwargs['pk'])
        return Match.objects.filter(tournament=tournament).select_related('player1', 'player2', 'winner')


class MatchDetailView(generics.RetrieveAPIView):
    queryset = Match.objects.select_related('player1', 'player2', 'winner', 'tournament')
    serializer_class = MatchSerializer
    permission_classes = [permissions.IsAuthenticated]


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

        serializer = MatchResultSerializer(data=request.data, context={'match': match})
        serializer.is_valid(raise_exception=True)

        winner_id = serializer.validated_data['winner']
        winner = match.player1 if match.player1_id == winner_id else match.player2
        complete_match(match, winner, serializer.validated_data.get('score', ''))

        return Response(MatchSerializer(match).data)
