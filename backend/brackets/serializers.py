from rest_framework import serializers

from brackets.models import Bracket, Match


class MatchSerializer(serializers.ModelSerializer):
    player1_email = serializers.SerializerMethodField()
    player2_email = serializers.SerializerMethodField()
    winner_email = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            'id', 'tournament', 'round_number', 'position',
            'player1', 'player1_email', 'player2', 'player2_email',
            'winner', 'winner_email', 'score', 'status', 'next_match',
        ]
        read_only_fields = fields

    def get_player1_email(self, obj):
        return obj.player1.email if obj.player1_id else None

    def get_player2_email(self, obj):
        return obj.player2.email if obj.player2_id else None

    def get_winner_email(self, obj):
        return obj.winner.email if obj.winner_id else None


class BracketSerializer(serializers.ModelSerializer):
    rounds = serializers.SerializerMethodField()

    class Meta:
        model = Bracket
        fields = ['id', 'tournament', 'total_rounds', 'created_at', 'rounds']

    def get_rounds(self, obj):
        matches = obj.matches.select_related('player1', 'player2', 'winner').order_by('round_number', 'position')
        grouped = {}
        for match in matches:
            grouped.setdefault(match.round_number, []).append(MatchSerializer(match).data)
        return [{'round_number': round_number, 'matches': grouped[round_number]} for round_number in sorted(grouped)]


class MatchResultSerializer(serializers.Serializer):
    winner = serializers.IntegerField()
    score = serializers.CharField(required=False, allow_blank=True, max_length=50)

    def validate_winner(self, value):
        match = self.context['match']
        valid_ids = {pid for pid in (match.player1_id, match.player2_id) if pid}
        if value not in valid_ids:
            raise serializers.ValidationError('Winner must be one of the two players in this match.')
        return value
