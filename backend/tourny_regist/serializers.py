from rest_framework import serializers

from tourny_regist.models import Registration


class RegistrationSerializer(serializers.ModelSerializer):
    tournament_name = serializers.CharField(source='tournament.name', read_only=True)
    player_email = serializers.EmailField(source='player.email', read_only=True)

    class Meta:
        model = Registration
        fields = [
            'id', 'tournament', 'tournament_name', 'player', 'player_email',
            'registered_at', 'checked_in', 'checked_in_at',
        ]
        read_only_fields = ['id', 'player', 'registered_at', 'checked_in', 'checked_in_at']


class RegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = ['tournament']

    def validate_tournament(self, tournament):
        if not tournament.is_registration_open:
            raise serializers.ValidationError('Registration is closed for this tournament.')
        if tournament.max_participants is not None:
            if tournament.registrations.count() >= tournament.max_participants:
                raise serializers.ValidationError('This tournament has reached its participant limit.')
        return tournament

    def validate(self, attrs):
        request = self.context['request']
        if Registration.objects.filter(tournament=attrs['tournament'], player=request.user).exists():
            raise serializers.ValidationError({'tournament': 'You are already registered for this tournament.'})
        return attrs

    def create(self, validated_data):
        return Registration.objects.create(player=self.context['request'].user, **validated_data)
