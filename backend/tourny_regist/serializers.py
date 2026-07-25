from django.utils import timezone
from rest_framework import serializers

from tourny_regist.cover_pool import assign_next_cover
from tourny_regist.models import Announcement, Registration, Team, TeamMembership, Tournament


def display_name(user):
    full_name = f'{user.first_name} {user.last_name}'.strip()
    return full_name or user.email


class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = Announcement
        fields = [
            'id', 'tournament', 'author_name', 'category', 'category_display',
            'title', 'message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'tournament', 'author_name', 'category_display', 'created_at', 'updated_at']

    def get_author_name(self, obj):
        return display_name(obj.author) if obj.author else None


class AnnouncementCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ['category', 'title', 'message']


DOCUMENT_FIELDS = [
    'company_registration_certificate', 'business_license',
    'organizer_cnic_front', 'organizer_cnic_back',
    'tax_certificate', 'sponsor_agreement',
]

APPLICATION_FIELDS = [
    'name', 'game', 'mode', 'bracket_format', 'team_size',
    'registration_fee', 'prize_pool', 'registration_deadline', 'starts_at', 'ends_at',
    'max_participants',
    'venue_name', 'venue_address', 'venue_map_link', 'venue_city', 'venue_province',
    'venue_country', 'venue_parking_available',
    'discord_server', 'room_id', 'platform',
    'contact_organizer_name', 'contact_company_name', 'contact_phone', 'contact_email',
    'contact_emergency_phone', 'contact_website',
    'social_facebook', 'social_instagram', 'social_discord', 'social_youtube',
] + DOCUMENT_FIELDS


class TournamentListSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='name', read_only=True)
    game = serializers.CharField(source='game.name', read_only=True)
    organizer = serializers.SerializerMethodField()
    start_date = serializers.DateTimeField(source='starts_at', read_only=True)
    end_date = serializers.DateTimeField(source='ends_at', read_only=True)
    teams = serializers.SerializerMethodField()
    phase = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = [
            'id', 'title', 'game', 'organizer', 'start_date', 'end_date', 'teams', 'phase',
            'status', 'rejection_reason', 'is_published', 'mode', 'bracket_format', 'team_size',
            'registration_fee', 'prize_pool', 'registration_deadline',
            'max_participants', 'is_registration_open',
            'venue_name', 'venue_city', 'venue_country', 'platform', 'cover_image_url',
        ]

    def get_organizer(self, obj):
        return obj.organizer.company_name if obj.organizer else None

    def get_teams(self, obj):
        return obj.registrations.count()

    def get_phase(self, obj):
        return 'live' if obj.starts_at <= timezone.now() else 'upcoming'

    def get_cover_image_url(self, obj):
        if not obj.cover_image:
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.cover_image.url) if request else obj.cover_image.url


class TournamentDetailSerializer(TournamentListSerializer):
    game_id = serializers.IntegerField(source='game.id', read_only=True)
    can_manage = serializers.SerializerMethodField()

    class Meta(TournamentListSerializer.Meta):
        fields = TournamentListSerializer.Meta.fields + [
            'game_id', 'can_manage',
            'venue_name', 'venue_address', 'venue_map_link', 'venue_city', 'venue_province',
            'venue_country', 'venue_parking_available',
            'discord_server', 'room_id', 'platform',
            'contact_organizer_name', 'contact_company_name', 'contact_phone', 'contact_email',
            'contact_emergency_phone', 'contact_website',
            'social_facebook', 'social_instagram', 'social_discord', 'social_youtube',
            'created_at', 'updated_at',
        ] + DOCUMENT_FIELDS

    def get_can_manage(self, obj):
        request = self.context.get('request')
        if request is None or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_staff:
            return True
        organizer_profile = getattr(user, 'organizer_profile', None)
        return organizer_profile is not None and obj.organizer_id == organizer_profile.pk


class TournamentApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = APPLICATION_FIELDS
        extra_kwargs = {
            'company_registration_certificate': {'required': True},
            'organizer_cnic_front': {'required': True},
            'organizer_cnic_back': {'required': True},
        }

    def validate(self, attrs):
        mode = attrs.get('mode')
        errors = {}

        if mode != Tournament.Mode.ONLINE:
            for field in ('venue_name', 'venue_address', 'venue_city', 'venue_country'):
                if not attrs.get(field):
                    errors[field] = 'This field is required for offline/hybrid tournaments.'
        if mode != Tournament.Mode.OFFLINE:
            if not attrs.get('platform'):
                errors['platform'] = 'This field is required for online/hybrid tournaments.'

        starts_at = attrs.get('starts_at')
        ends_at = attrs.get('ends_at')
        registration_deadline = attrs.get('registration_deadline')
        if starts_at and ends_at and ends_at < starts_at:
            errors['ends_at'] = 'End date must be on or after the start date.'
        if starts_at and registration_deadline and registration_deadline > starts_at:
            errors['registration_deadline'] = 'Registration deadline must be before the tournament starts.'

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        tournament = Tournament.objects.create(
            organizer=request.user.organizer_profile,
            created_by=request.user,
            status=Tournament.Status.PENDING,
            **validated_data,
        )
        assign_next_cover(tournament)
        return tournament


class TournamentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = APPLICATION_FIELDS

    def validate(self, attrs):
        def current(field):
            return attrs[field] if field in attrs else getattr(self.instance, field)

        mode = current('mode')
        errors = {}

        if mode != Tournament.Mode.ONLINE:
            for field in ('venue_name', 'venue_address', 'venue_city', 'venue_country'):
                if not current(field):
                    errors[field] = 'This field is required for offline/hybrid tournaments.'
        if mode != Tournament.Mode.OFFLINE:
            if not current('platform'):
                errors['platform'] = 'This field is required for online/hybrid tournaments.'

        starts_at = current('starts_at')
        ends_at = current('ends_at')
        registration_deadline = current('registration_deadline')
        if starts_at and ends_at and ends_at < starts_at:
            errors['ends_at'] = 'End date must be on or after the start date.'
        if starts_at and registration_deadline and registration_deadline > starts_at:
            errors['registration_deadline'] = 'Registration deadline must be before the tournament starts.'

        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AdminTournamentSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source='game.name', read_only=True)
    organizer_name = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = Tournament
        fields = [
            'id', 'name', 'game', 'game_name', 'organizer', 'organizer_name', 'created_by_email',
            'status', 'rejection_reason', 'is_published', 'mode', 'bracket_format', 'team_size',
            'registration_fee', 'prize_pool', 'registration_deadline', 'starts_at', 'ends_at',
            'max_participants', 'is_registration_open',
            'venue_name', 'venue_address', 'venue_map_link', 'venue_city', 'venue_province',
            'venue_country', 'venue_parking_available',
            'discord_server', 'room_id', 'platform',
            'contact_organizer_name', 'contact_company_name', 'contact_phone', 'contact_email',
            'contact_emergency_phone', 'contact_website',
            'social_facebook', 'social_instagram', 'social_discord', 'social_youtube',
            'created_at', 'updated_at',
        ] + DOCUMENT_FIELDS

    def get_organizer_name(self, obj):
        return obj.organizer.company_name if obj.organizer else None


class AdminTournamentUpdateSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(source='rejection_reason', required=False, allow_blank=True)

    class Meta:
        model = Tournament
        fields = ['status', 'reason']

    def update(self, instance, validated_data):
        if validated_data.get('status') == Tournament.Status.APPROVED and 'rejection_reason' not in validated_data:
            validated_data['rejection_reason'] = ''
        return super().update(instance, validated_data)


class TeamMembershipSerializer(serializers.ModelSerializer):
    player_id = serializers.IntegerField(source='player.id', read_only=True)
    email = serializers.EmailField(source='player.email', read_only=True)
    name = serializers.SerializerMethodField()
    is_captain = serializers.SerializerMethodField()

    class Meta:
        model = TeamMembership
        fields = ['player_id', 'email', 'name', 'is_captain', 'joined_at']

    def get_name(self, obj):
        return display_name(obj.player)

    def get_is_captain(self, obj):
        return obj.team.captain_id == obj.player_id


class TeamSerializer(serializers.ModelSerializer):
    members = TeamMembershipSerializer(many=True, read_only=True)
    is_registered = serializers.SerializerMethodField()
    registration_id = serializers.SerializerMethodField()

    class Meta:
        model = Team
        fields = [
            'id', 'tournament', 'name', 'captain', 'invite_code',
            'members', 'is_registered', 'registration_id', 'created_at',
        ]
        read_only_fields = ['id', 'tournament', 'captain', 'invite_code', 'created_at']

    def _registration(self, obj):
        try:
            return obj.registration
        except Registration.DoesNotExist:
            return None

    def get_is_registered(self, obj):
        return self._registration(obj) is not None

    def get_registration_id(self, obj):
        registration = self._registration(obj)
        return registration.id if registration else None


class TeamCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['name']


class TeamJoinSerializer(serializers.Serializer):
    invite_code = serializers.CharField()


REGISTRATION_FORM_FIELDS = [
    'full_name', 'gaming_username', 'phone_number', 'contact_email', 'country', 'city',
    'emergency_contact_name', 'emergency_contact_phone', 'platform', 'platform_username',
    'accepted_rules', 'accepted_code_of_conduct', 'payment_proof',
]


class RegistrationSerializer(serializers.ModelSerializer):
    tournament_name = serializers.CharField(source='tournament.name', read_only=True)
    player_email = serializers.EmailField(source='player.email', read_only=True)
    team_name = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = [
            'id', 'tournament', 'tournament_name', 'player', 'player_email', 'team', 'team_name',
            'status', 'rejection_reason',
            'registered_at', 'checked_in', 'checked_in_at',
        ] + REGISTRATION_FORM_FIELDS
        read_only_fields = [
            'id', 'player', 'team', 'status', 'rejection_reason', 'registered_at', 'checked_in', 'checked_in_at',
        ] + REGISTRATION_FORM_FIELDS

    def get_team_name(self, obj):
        return obj.team.name if obj.team_id else None


class RegistrationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = ['tournament'] + REGISTRATION_FORM_FIELDS
        extra_kwargs = {
            'full_name': {'required': True},
            'gaming_username': {'required': True},
            'phone_number': {'required': True},
            'contact_email': {'required': True},
            'country': {'required': True},
            'city': {'required': True},
        }

    def validate_tournament(self, tournament):
        if tournament.team_size > 1:
            raise serializers.ValidationError(
                'This tournament requires team registration — join or create a team first.',
            )
        if not tournament.is_registration_open:
            raise serializers.ValidationError('Registration is closed for this tournament.')
        if tournament.registration_deadline and timezone.now() > tournament.registration_deadline:
            raise serializers.ValidationError('The registration deadline for this tournament has passed.')
        if tournament.max_participants is not None:
            if tournament.registrations.count() >= tournament.max_participants:
                raise serializers.ValidationError('This tournament has reached its participant limit.')
        return tournament

    def validate(self, attrs):
        request = self.context['request']
        tournament = attrs.get('tournament')

        if Registration.objects.filter(tournament=tournament, player=request.user).exists():
            raise serializers.ValidationError({'tournament': 'You are already registered for this tournament.'})

        errors = {}
        if not attrs.get('accepted_rules'):
            errors['accepted_rules'] = 'You must agree to follow all tournament rules.'
        if not attrs.get('accepted_code_of_conduct'):
            errors['accepted_code_of_conduct'] = 'You must agree to the code of conduct.'
        if tournament and tournament.mode != Tournament.Mode.OFFLINE:
            if not attrs.get('platform'):
                errors['platform'] = 'This field is required for online/hybrid tournaments.'
            if not attrs.get('platform_username'):
                errors['platform_username'] = 'This field is required for online/hybrid tournaments.'
        if tournament and tournament.registration_fee and tournament.registration_fee > 0 and not attrs.get('payment_proof'):
            errors['payment_proof'] = 'Please upload proof of payment for the registration fee.'

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        tournament = validated_data['tournament']
        status = (
            Registration.Status.PENDING
            if tournament.registration_fee and tournament.registration_fee > 0
            else Registration.Status.APPROVED
        )
        return Registration.objects.create(
            player=self.context['request'].user, status=status, **validated_data,
        )


class RegistrationReviewSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(source='rejection_reason', required=False, allow_blank=True)

    class Meta:
        model = Registration
        fields = ['status', 'reason']

    def update(self, instance, validated_data):
        new_status = validated_data.get('status')
        if new_status == Registration.Status.APPROVED and 'rejection_reason' not in validated_data:
            validated_data['rejection_reason'] = ''
        if new_status == Registration.Status.REJECTED:
            # A rejected registration can't stay checked in for a bracket seeding.
            validated_data['checked_in'] = False
            validated_data['checked_in_at'] = None
        return super().update(instance, validated_data)
