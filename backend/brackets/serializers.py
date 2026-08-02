from rest_framework import serializers

from brackets.models import Bracket, Match
from brackets.services import standings as compute_standings
from tourny_regist.models import Team


def display_name(user, tournament=None):
    if tournament is not None and tournament.team_size > 1:
        team = Team.objects.filter(tournament=tournament, captain=user).first()
        if team is not None:
            return team.name
    full_name = f'{user.first_name} {user.last_name}'.strip()
    # Bracket/match data (this function feeds the *_email serializer fields
    # below, and the standings payload) is visible to any authenticated user,
    # not just tournament participants — never fall back to a real email
    # address here, since that would leak a player's PII to strangers just
    # because they never got around to setting a display name.
    return full_name or f'Player #{user.pk}'


class MatchSerializer(serializers.ModelSerializer):
    player1_email = serializers.SerializerMethodField()
    player2_email = serializers.SerializerMethodField()
    winner_email = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            'id', 'tournament', 'bracket_side', 'group_label', 'round_number', 'position',
            'player1', 'player1_email', 'player2', 'player2_email',
            'winner', 'winner_email', 'score', 'status', 'next_match',
        ]
        read_only_fields = fields

    def get_player1_email(self, obj):
        return display_name(obj.player1, obj.tournament) if obj.player1_id else None

    def get_player2_email(self, obj):
        return display_name(obj.player2, obj.tournament) if obj.player2_id else None

    def get_winner_email(self, obj):
        return display_name(obj.winner, obj.tournament) if obj.winner_id else None


class BracketSerializer(serializers.ModelSerializer):
    rounds = serializers.SerializerMethodField()
    standings = serializers.SerializerMethodField()

    class Meta:
        model = Bracket
        fields = ['id', 'tournament', 'format', 'total_rounds', 'created_at', 'rounds', 'standings']

    @staticmethod
    def _grouped_by_round(matches):
        grouped = {}
        for match in matches:
            grouped.setdefault(match.round_number, []).append(MatchSerializer(match).data)
        return [{'round_number': round_number, 'matches': grouped[round_number]} for round_number in sorted(grouped)]

    @staticmethod
    def _standings_payload(rows, tournament=None):
        return [
            {
                'player_id': row['player'].pk,
                'name': display_name(row['player'], tournament),
                'wins': row['wins'],
                'played': row['played'],
            }
            for row in rows
        ]

    def get_rounds(self, obj):
        matches = list(obj.matches.select_related('player1', 'player2', 'winner').order_by('round_number', 'position'))

        if obj.format in (Bracket.Format.DOUBLE, Bracket.Format.GUARANTEE3):
            shape = {
                'winners': self._grouped_by_round([m for m in matches if m.bracket_side == Match.Side.WINNERS]),
                'losers': self._grouped_by_round([m for m in matches if m.bracket_side == Match.Side.LOSERS]),
                'grand_final': self._grouped_by_round([m for m in matches if m.bracket_side == Match.Side.GRAND_FINAL]),
            }
            if obj.format == Bracket.Format.GUARANTEE3:
                shape['guarantee'] = self._grouped_by_round([m for m in matches if m.bracket_side == Match.Side.GUARANTEE])
            return shape

        if obj.format == Bracket.Format.GROUP_PLAYOFF:
            groups = {}
            playoff_matches = []
            for m in matches:
                if m.bracket_side == Match.Side.GROUP:
                    groups.setdefault(m.group_label, []).append(m)
                elif m.bracket_side == Match.Side.WINNERS:
                    playoff_matches.append(m)
            return {
                'groups': {label: self._grouped_by_round(group_matches) for label, group_matches in sorted(groups.items())},
                'playoff': self._grouped_by_round(playoff_matches),
            }

        return self._grouped_by_round(matches)

    def get_standings(self, obj):
        tournament = obj.tournament

        if obj.format in (Bracket.Format.ROUND_ROBIN, Bracket.Format.SWISS):
            return self._standings_payload(compute_standings(tournament), tournament)

        if obj.format == Bracket.Format.GROUP_PLAYOFF:
            group_matches = list(obj.matches.filter(bracket_side=Match.Side.GROUP).select_related('player1', 'player2'))
            all_players = [r.player for r in tournament.registrations.order_by('registered_at')]
            labels = sorted({m.group_label for m in group_matches})
            result = {}
            for label in labels:
                ids_in_group = set()
                for m in group_matches:
                    if m.group_label == label:
                        ids_in_group.add(m.player1_id)
                        ids_in_group.add(m.player2_id)
                group_players = [p for p in all_players if p.pk in ids_in_group]
                result[label] = self._standings_payload(compute_standings(tournament, group_players), tournament)
            return result

        return None


class MatchResultSerializer(serializers.Serializer):
    winner = serializers.IntegerField()
    score = serializers.CharField(required=False, allow_blank=True, max_length=50)

    def validate_winner(self, value):
        match = self.context['match']
        valid_ids = {pid for pid in (match.player1_id, match.player2_id) if pid}
        if value not in valid_ids:
            raise serializers.ValidationError('Winner must be one of the two players in this match.')
        return value
