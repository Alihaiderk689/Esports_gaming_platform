from django.db import IntegrityError
from django.utils import timezone
from rest_framework import serializers

from core.models import AdminReviewRequest, AuditLog
from tourny_regist.game_banners import assign_game_banner
from tourny_regist.models import Announcement, Registration, Team, TeamMembership, Tournament, TournamentRuleVersion
from tourny_regist.validation import validate_tournament_structure


def display_name(user):
    full_name = f'{user.first_name} {user.last_name}'.strip()
    # Announcements and rule-version history are visible to anyone who can
    # see the tournament itself (see TournamentAnnouncementsView/
    # TournamentRulesView's IsPublicOrOwner gate) — for a published
    # tournament that includes the general public, not just stakeholders.
    # Never fall back to a real email address here; mirrors
    # brackets/serializers.py:display_name for the same reason.
    return full_name or f'User #{user.pk}'


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


RULE_SECTION_FIELDS = [
    'match_format_rules', 'conduct_rules', 'scoring_rules', 'penalties_and_disqualification', 'additional_notes',
]


class TournamentRuleVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TournamentRuleVersion
        fields = ['id', 'tournament', 'version', 'created_by_name', 'created_at'] + RULE_SECTION_FIELDS
        read_only_fields = fields

    def get_created_by_name(self, obj):
        return display_name(obj.created_by) if obj.created_by else None


class TournamentRuleVersionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentRuleVersion
        fields = RULE_SECTION_FIELDS

    def validate(self, attrs):
        if not any((attrs.get(f) or '').strip() for f in RULE_SECTION_FIELDS):
            raise serializers.ValidationError({'detail': 'At least one rules section must have content to publish.'})
        return attrs


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
    'check_in_start', 'check_in_end',
    'max_participants', 'min_participants', 'game_version', 'server_region',
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
    game_slug = serializers.CharField(source='game.slug', read_only=True)
    organizer = serializers.SerializerMethodField()
    start_date = serializers.DateTimeField(source='starts_at', read_only=True)
    end_date = serializers.DateTimeField(source='ends_at', read_only=True)
    teams = serializers.SerializerMethodField()
    phase = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Tournament
        fields = [
            'id', 'title', 'game', 'game_slug', 'organizer', 'start_date', 'end_date', 'teams', 'phase',
            'status', 'rejection_reason', 'is_published', 'mode', 'bracket_format', 'team_size',
            'registration_fee', 'prize_pool', 'registration_deadline', 'check_in_start', 'check_in_end',
            'max_participants', 'min_participants', 'is_registration_open', 'game_version', 'server_region',
            'cancellation_reason', 'cancelled_at',
            'venue_name', 'venue_city', 'venue_country', 'platform', 'cover_image_url',
        ]

    def get_organizer(self, obj):
        return obj.organizer.company_name if obj.organizer else None

    def get_teams(self, obj):
        # List views annotate teams_count on the queryset (Count('registrations'))
        # to avoid a query per tournament; TournamentDetailSerializer (single
        # object, no N+1 concern) falls back to the direct count.
        teams_count = getattr(obj, 'teams_count', None)
        return teams_count if teams_count is not None else obj.registrations.count()

    def get_phase(self, obj):
        if obj.starts_at is None:
            return None
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
        errors = {}
        validate_tournament_structure(attrs.get, errors)

        starts_at = attrs.get('starts_at')
        registration_deadline = attrs.get('registration_deadline')
        if not starts_at:
            errors['starts_at'] = 'Start date is required.'
        elif starts_at <= timezone.now():
            errors['starts_at'] = 'Tournament start date must be in the future.'
        if registration_deadline and registration_deadline <= timezone.now():
            errors['registration_deadline'] = 'Registration deadline must be in the future.'

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
        assign_game_banner(tournament)
        return tournament


class TournamentDraftSerializer(serializers.ModelSerializer):
    """Creates a Tournament in DRAFT status. Only `name`/`game` are actually
    required (the model fields they map to are non-nullable); everything else
    in APPLICATION_FIELDS is already optional at the model level and stays
    that way here — full strictness is deferred to submit_tournament()
    (tourny_regist.lifecycle), which reuses TournamentApplicationSerializer's
    rules against the draft's saved state at submit time."""
    class Meta:
        model = Tournament
        fields = APPLICATION_FIELDS

    def validate(self, attrs):
        errors = {}
        # Ordering checks only — no mode-conditional "required" checks, no
        # future-date requirement. A draft may be deliberately incomplete.
        validate_tournament_structure(attrs.get, errors, require_mode_fields=False)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        request = self.context['request']
        tournament = Tournament.objects.create(
            organizer=request.user.organizer_profile,
            created_by=request.user,
            status=Tournament.Status.DRAFT,
            **validated_data,
        )
        assign_game_banner(tournament)
        return tournament


class TournamentRescheduleRequestSerializer(serializers.Serializer):
    reason = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    registration_deadline = serializers.DateTimeField(required=False, allow_null=True)


class TournamentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tournament
        fields = APPLICATION_FIELDS

    def validate(self, attrs):
        def current(field):
            return attrs[field] if field in attrs else getattr(self.instance, field)

        errors = {}
        # A still-incomplete DRAFT may legitimately have no venue/platform yet —
        # only enforce those once the organizer is editing a submitted tournament.
        validate_tournament_structure(
            current, errors, require_mode_fields=self.instance.status != Tournament.Status.DRAFT,
        )

        # Only reject a past date when the organizer is actually *changing* it to
        # that past value — a tournament that has already started (or whose
        # deadline has already passed) must stay editable for its other fields,
        # since the frontend resends the full form (including unmodified dates)
        # on every save.
        now = timezone.now()
        if (
            'starts_at' in attrs and attrs['starts_at'] is not None
            and attrs['starts_at'] != self.instance.starts_at and attrs['starts_at'] <= now
        ):
            errors['starts_at'] = 'Tournament start date must be in the future.'
        if (
            'registration_deadline' in attrs
            and attrs['registration_deadline'] is not None
            and attrs['registration_deadline'] != self.instance.registration_deadline
            and attrs['registration_deadline'] <= now
        ):
            errors['registration_deadline'] = 'Registration deadline must be in the future.'

        # These three determine the shape of every registration/team/bracket
        # already collected — changing them afterward doesn't retroactively
        # fix anything already on record, it just makes it inconsistent with
        # the tournament's new definition (a roster sized for the old
        # team_size, a bracket built for the old bracket_format, players who
        # registered for a now-different game). Once anything has actually
        # signed up, these are frozen; DRAFT tournaments (nothing to
        # invalidate yet) are unaffected.
        structural_fields = ('game', 'team_size', 'bracket_format')
        changed_structural = [
            f for f in structural_fields if f in attrs and attrs[f] != getattr(self.instance, f)
        ]
        if changed_structural and (
            self.instance.registrations.exists()
            or self.instance.teams.exists()
            or hasattr(self.instance, 'bracket')
        ):
            for f in changed_structural:
                errors[f] = 'This cannot be changed once players have registered for this tournament.'

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
            'check_in_start', 'check_in_end',
            'max_participants', 'min_participants', 'is_registration_open', 'game_version', 'server_region',
            'cancellation_reason', 'cancelled_by', 'cancelled_at',
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

    def validate_status(self, new_status):
        # Admin review only ever decides a submitted (PENDING) tournament —
        # DRAFT/CANCELLED have their own dedicated workflows (submit/cancel in
        # tourny_regist.lifecycle) and must not be reachable by an arbitrary
        # PATCH here, and APPROVED/REJECTED aren't valid targets from
        # anywhere except PENDING.
        if self.instance.status != Tournament.Status.PENDING:
            raise serializers.ValidationError('Only a pending tournament can be approved or rejected.')
        if new_status not in (Tournament.Status.APPROVED, Tournament.Status.REJECTED):
            raise serializers.ValidationError('Admin review can only approve or reject a pending tournament.')
        return new_status

    def update(self, instance, validated_data):
        if validated_data.get('status') == Tournament.Status.APPROVED and 'rejection_reason' not in validated_data:
            validated_data['rejection_reason'] = ''
        return super().update(instance, validated_data)


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source='actor.email', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'actor_email', 'reason', 'metadata', 'created_at']
        read_only_fields = fields


class AdminReviewRequestSerializer(serializers.ModelSerializer):
    requested_by_email = serializers.EmailField(source='requested_by.email', read_only=True)
    decided_by_email = serializers.EmailField(source='decided_by.email', read_only=True)
    target_label = serializers.SerializerMethodField()
    target_tournament_id = serializers.SerializerMethodField()

    class Meta:
        model = AdminReviewRequest
        fields = [
            'id', 'request_type', 'reason', 'object_id', 'target_label', 'target_tournament_id',
            'requested_by_email', 'status', 'decided_by_email', 'decision_reason',
            'created_at', 'decided_at',
        ]
        read_only_fields = fields

    def get_target_label(self, obj):
        # TOURNAMENT_CANCELLATION and BRACKET_RESET both target the Tournament
        # directly (a Bracket row may not even exist by the time this is read —
        # reset_bracket deletes it — so the request deliberately never points
        # at one).
        if obj.request_type in (
            AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION, AdminReviewRequest.RequestType.BRACKET_RESET,
        ):
            return obj.target.name
        if obj.request_type == AdminReviewRequest.RequestType.REGISTRATION_CANCELLATION:
            registration = obj.target
            return f'{registration.player.email} — {registration.tournament.name}'
        return None

    def get_target_tournament_id(self, obj):
        if obj.request_type in (
            AdminReviewRequest.RequestType.TOURNAMENT_CANCELLATION, AdminReviewRequest.RequestType.BRACKET_RESET,
        ):
            return obj.object_id
        if obj.request_type == AdminReviewRequest.RequestType.REGISTRATION_CANCELLATION:
            return obj.target.tournament_id
        return None


class AdminReviewRequestDecideSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[AdminReviewRequest.Status.APPROVED, AdminReviewRequest.Status.REJECTED])
    reason = serializers.CharField(required=False, allow_blank=True)


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
            'is_locked', 'locked_at',
        ]
        read_only_fields = [
            'id', 'tournament', 'captain', 'invite_code', 'created_at', 'is_locked', 'locked_at',
        ]

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
    is_no_show = serializers.SerializerMethodField()
    rules_outdated = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = [
            'id', 'tournament', 'tournament_name', 'player', 'player_email', 'team', 'team_name',
            'status', 'rejection_reason', 'is_no_show', 'seed',
            'cancellation_reason', 'cancelled_at', 'disqualification_reason', 'disqualified_at',
            'registered_at', 'checked_in', 'checked_in_at',
            'accepted_rules_version', 'rules_outdated',
        ] + REGISTRATION_FORM_FIELDS
        # `seed` is read-only here by design — writes only ever go through
        # TournamentSeedingView, which bulk-updates it directly and is the
        # single place the "no seed changes once a bracket exists" rule lives.
        # `accepted_rules_version` is stamped server-side only, in
        # RegistrationCreateSerializer.create() / RegistrationAcknowledgeRulesView
        # — never client-writable, for the same reason `checked_in` isn't.
        read_only_fields = [
            'id', 'player', 'team', 'status', 'rejection_reason', 'seed',
            'cancellation_reason', 'cancelled_at', 'disqualification_reason', 'disqualified_at',
            'registered_at', 'checked_in', 'checked_in_at', 'accepted_rules_version',
        ] + REGISTRATION_FORM_FIELDS

    def get_team_name(self, obj):
        return obj.team.name if obj.team_id else None

    def get_is_no_show(self, obj):
        return (
            obj.status == Registration.Status.APPROVED
            and not obj.checked_in
            and obj.tournament.starts_at is not None
            and obj.tournament.starts_at < timezone.now()
        )

    def get_rules_outdated(self, obj):
        """True when the organizer has published a rules version since this
        player last acknowledged one — including never having acknowledged any,
        if a version now exists. Drives the "please re-read the rules" prompt;
        never blocks anything by itself (that's RegistrationAcknowledgeRulesView's
        job if the organizer wants to require it)."""
        current = obj.tournament.current_rule_version()
        if current is None:
            return False
        return obj.accepted_rules_version != current.version


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
        if tournament.status != Tournament.Status.APPROVED:
            raise serializers.ValidationError('This tournament is not open for registration.')
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
        current_rules = tournament.current_rule_version()
        try:
            return Registration.objects.create(
                player=self.context['request'].user, status=status,
                accepted_rules_version=current_rules.version if current_rules else None,
                **validated_data,
            )
        except IntegrityError:
            # The pre-check in validate() above closes this for the normal case;
            # this only catches two simultaneous submits racing past that check.
            raise serializers.ValidationError({'tournament': 'You are already registered for this tournament.'})


class RegistrationReviewSerializer(serializers.ModelSerializer):
    reason = serializers.CharField(source='rejection_reason', required=False, allow_blank=True)

    class Meta:
        model = Registration
        fields = ['status', 'reason']

    def validate(self, attrs):
        # DISQUALIFIED/CANCELLED are terminal states reached only through
        # lifecycle.disqualify_registration (which forfeits a live match)
        # or cancel_registration (which may itself have required admin
        # review) — this endpoint is meant for reviewing a payment/entry
        # (approve/reject, in either direction), not for silently undoing
        # one of those with no forfeit-reversal, no reason requirement, and
        # no link back to why the original decision was made.
        if self.instance.status in (Registration.Status.DISQUALIFIED, Registration.Status.CANCELLED):
            raise serializers.ValidationError({
                'detail': f'This registration is already {self.instance.status} and cannot be reviewed here.',
            })
        return attrs

    def update(self, instance, validated_data):
        new_status = validated_data.get('status')
        if new_status == Registration.Status.APPROVED and 'rejection_reason' not in validated_data:
            validated_data['rejection_reason'] = ''
        if new_status == Registration.Status.REJECTED:
            # A rejected registration can't stay checked in for a bracket seeding.
            validated_data['checked_in'] = False
            validated_data['checked_in_at'] = None
        return super().update(instance, validated_data)
