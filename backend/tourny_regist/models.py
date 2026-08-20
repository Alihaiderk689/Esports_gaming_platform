from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.crypto import get_random_string

from core.storage import CloudinarySignedStorage
from core.validators import validate_document_file, validate_phone_number


class Tournament(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending Admin Approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'

    class Mode(models.TextChoices):
        ONLINE = 'online', 'Online'
        OFFLINE = 'offline', 'Offline'
        HYBRID = 'hybrid', 'Hybrid'

    class BracketFormat(models.TextChoices):
        SINGLE = 'single', 'Single Elimination'
        DOUBLE = 'double', 'Double Elimination'
        GUARANTEE3 = 'guarantee3', '3-Game Guarantee'
        ROUND_ROBIN = 'round_robin', 'Round Robin'
        SWISS = 'swiss', 'Swiss System'
        GROUP_PLAYOFF = 'group_playoff', 'Group Stage + Playoff'

    name = models.CharField(max_length=200)
    cover_image = models.ImageField(upload_to='tournaments/covers/%Y/%m/', blank=True, null=True)
    game = models.ForeignKey('games.Game', related_name='tournaments', on_delete=models.CASCADE)
    # PROTECT: an Organizer with tournaments on record should never be
    # deletable outright — see Organizer.user's docstring for the same
    # reasoning one level up (deleting the *user* is already blocked there;
    # this is the equivalent backstop if an Organizer row is ever deleted
    # directly instead).
    organizer = models.ForeignKey(
        'organizer.Organizer', related_name='tournaments', on_delete=models.PROTECT, null=True, blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='created_tournaments',
        null=True, blank=True, on_delete=models.SET_NULL,
    )

    # Set once by brackets.services.finalize_tournament_champion when the
    # deciding match (or, for round robin/Swiss, the final round) completes —
    # see that function for the per-format definition of "decided". Left null
    # otherwise, including for tournaments that never generate a bracket.
    champion = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='tournament_wins',
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    champion_declared_at = models.DateTimeField(null=True, blank=True)
    # Set when the champion dismisses the one-time "Congratulations" reveal on
    # their dashboard, so it doesn't pop up again on every subsequent login.
    champion_seen_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)

    # Set by tourny_regist.lifecycle.cancel_tournament. cancelled_by uses
    # SET_NULL (not CASCADE) so deleting the actor's account doesn't delete
    # cancellation history — same rationale as champion/created_by above.
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', null=True, blank=True, on_delete=models.SET_NULL,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.ONLINE)
    bracket_format = models.CharField(max_length=20, choices=BracketFormat.choices, default=BracketFormat.SINGLE)
    team_size = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    registration_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)],
    )
    prize_pool = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)],
    )

    registration_deadline = models.DateTimeField(null=True, blank=True)
    # Nullable so a draft can exist before the organizer has picked a start
    # date; every non-draft path (submit for approval, direct creation via
    # TournamentApplicationSerializer) still requires it — see
    # tourny_regist.lifecycle.validate_tournament_fields.
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    check_in_start = models.DateTimeField(null=True, blank=True)
    check_in_end = models.DateTimeField(null=True, blank=True)

    max_participants = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    min_participants = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    is_registration_open = models.BooleanField(default=True)

    game_version = models.CharField(max_length=50, blank=True)
    server_region = models.CharField(max_length=100, blank=True)

    # Venue (relevant when mode is offline/hybrid)
    venue_name = models.CharField(max_length=200, blank=True)
    venue_address = models.TextField(blank=True)
    venue_map_link = models.URLField(blank=True)
    venue_city = models.CharField(max_length=100, blank=True)
    venue_province = models.CharField(max_length=100, blank=True)
    venue_country = models.CharField(max_length=100, blank=True)
    venue_parking_available = models.BooleanField(default=False)

    # Online (relevant when mode is online/hybrid)
    discord_server = models.CharField(max_length=255, blank=True)
    room_id = models.CharField(max_length=100, blank=True)
    platform = models.CharField(max_length=100, blank=True)

    # Contact details
    contact_organizer_name = models.CharField(max_length=150, blank=True)
    contact_company_name = models.CharField(max_length=200, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True, validators=[validate_phone_number])
    contact_email = models.EmailField(blank=True)
    contact_emergency_phone = models.CharField(max_length=30, blank=True, validators=[validate_phone_number])
    contact_website = models.URLField(blank=True)

    # Social media (optional)
    social_facebook = models.URLField(blank=True)
    social_instagram = models.URLField(blank=True)
    social_discord = models.URLField(blank=True)
    social_youtube = models.URLField(blank=True)

    # Documents — all use CloudinarySignedStorage since these are compliance/
    # identity documents, not public assets like cover_image above.
    company_registration_certificate = models.FileField(
        upload_to='tournaments/company_registration_certificate/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    business_license = models.FileField(
        upload_to='tournaments/business_license/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    organizer_cnic_front = models.FileField(
        upload_to='tournaments/organizer_cnic_front/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    organizer_cnic_back = models.FileField(
        upload_to='tournaments/organizer_cnic_back/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    tax_certificate = models.FileField(
        upload_to='tournaments/tax_certificate/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )
    sponsor_agreement = models.FileField(
        upload_to='tournaments/sponsor_agreement/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(ends_at__isnull=True) | models.Q(starts_at__isnull=True) | models.Q(ends_at__gte=models.F('starts_at')),
                name='tournament_ends_at_after_starts_at',
            ),
            models.CheckConstraint(
                check=(
                    models.Q(min_participants__isnull=True)
                    | models.Q(max_participants__isnull=True)
                    | models.Q(min_participants__lte=models.F('max_participants'))
                ),
                name='tournament_min_lte_max_participants',
            ),
        ]

    def __str__(self):
        return self.name

    def current_rule_version(self):
        """The latest published TournamentRuleVersion, or None if the organizer
        has never published one — most tournaments, since this is opt-in."""
        return self.rule_versions.order_by('-version').first()


class Announcement(models.Model):
    class Category(models.TextChoices):
        MATCH_TIMING = 'match_timing', 'Match Timing'
        DELAY = 'delay', 'Delay'
        RULE_CHANGE = 'rule_change', 'Rule Change'
        VENUE_UPDATE = 'venue_update', 'Venue Update'
        GENERAL = 'general', 'General'

    tournament = models.ForeignKey(Tournament, related_name='announcements', on_delete=models.CASCADE)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', null=True, blank=True, on_delete=models.SET_NULL,
    )
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    title = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.tournament_id})'


class TournamentRuleVersion(models.Model):
    """A published snapshot of a tournament's rules. Publishing never edits an
    existing row — it creates the next `version` — so a past version stays
    exactly what it was when someone acknowledged it (Registration.
    accepted_rules_version records which one), and organizers get a real
    changelog instead of a single mutable rules blob.

    Split into named sections rather than one freeform text field so each
    concern (format, conduct, scoring, penalties) can be read, diffed, and
    required independently — "structured," not just versioned."""

    tournament = models.ForeignKey(Tournament, related_name='rule_versions', on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    match_format_rules = models.TextField(blank=True)
    conduct_rules = models.TextField(blank=True)
    scoring_rules = models.TextField(blank=True)
    penalties_and_disqualification = models.TextField(blank=True)
    additional_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'version'], name='unique_tournament_rule_version'),
        ]
        ordering = ['-version']

    def __str__(self):
        return f'Rules v{self.version} for tournament {self.tournament_id}'

    def is_empty(self):
        return not any([
            self.match_format_rules.strip(), self.conduct_rules.strip(), self.scoring_rules.strip(),
            self.penalties_and_disqualification.strip(), self.additional_notes.strip(),
        ])


def _generate_invite_code():
    return get_random_string(8).upper()


class Team(models.Model):
    tournament = models.ForeignKey(Tournament, related_name='teams', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    captain = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='captained_teams', on_delete=models.CASCADE,
    )
    invite_code = models.CharField(max_length=10, unique=True, default=_generate_invite_code)
    created_at = models.DateTimeField(auto_now_add=True)

    # Set by tourny_regist.lifecycle.lock_team_roster / unlock_team_roster.
    # Locking blocks TeamJoinView/TeamLeaveView; unlocking is staff-only (see
    # that view) since re-opening a roster after competitive activity has
    # started is exactly the kind of change spec section 12 wants gated.
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', null=True, blank=True, on_delete=models.SET_NULL,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'name'], name='unique_team_name_per_tournament'),
        ]

    def __str__(self):
        return f'{self.name} ({self.tournament_id})'


class TeamMembership(models.Model):
    team = models.ForeignKey(Team, related_name='members', on_delete=models.CASCADE)
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='team_memberships', on_delete=models.CASCADE,
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['team', 'player'], name='unique_team_membership'),
        ]

    def __str__(self):
        return f'{self.player_id} -> {self.team_id}'


class Registration(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Payment Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled by Organizer'
        DISQUALIFIED = 'disqualified', 'Disqualified'

    tournament = models.ForeignKey(Tournament, related_name='registrations', on_delete=models.CASCADE)
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='tournament_registrations', on_delete=models.CASCADE,
    )
    team = models.OneToOneField(
        Team, related_name='registration', null=True, blank=True, on_delete=models.SET_NULL,
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED)
    rejection_reason = models.TextField(blank=True)

    # Set by tourny_regist.lifecycle.cancel_registration — an organizer-
    # initiated soft-cancel, distinct from a player's own self-withdrawal
    # (RegistrationDeleteView, a hard delete of their own row).
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', null=True, blank=True, on_delete=models.SET_NULL,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Set by match-administration disqualification actions (brackets stage).
    disqualification_reason = models.TextField(blank=True)
    disqualified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name='+', null=True, blank=True, on_delete=models.SET_NULL,
    )
    disqualified_at = models.DateTimeField(null=True, blank=True)

    # Manual bracket seed (1 = top seed). Null means "no manual seed" — see
    # brackets.services.seed_players, which falls back to registration order
    # for anyone without one. Organizer-settable only before a bracket exists
    # (tourny_regist.views.TournamentSeedingView) — once one does, reseeding
    # requires resetting it first (brackets.services.reset_bracket).
    seed = models.PositiveIntegerField(null=True, blank=True)

    full_name = models.CharField(max_length=150, blank=True)
    gaming_username = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=30, blank=True, validators=[validate_phone_number])
    contact_email = models.EmailField(blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True)
    emergency_contact_phone = models.CharField(max_length=30, blank=True, validators=[validate_phone_number])
    platform = models.CharField(max_length=100, blank=True)
    platform_username = models.CharField(max_length=100, blank=True)
    accepted_rules = models.BooleanField(default=False)
    accepted_code_of_conduct = models.BooleanField(default=False)
    # Which TournamentRuleVersion.version the player actually agreed to at
    # registration time (see RegistrationCreateSerializer.create) — plain int,
    # not a FK, so it stays meaningful even if that exact version row is ever
    # pruned. Null means either no versioned rules existed yet when they
    # registered, or (team registration) acceptance isn't collected at all.
    accepted_rules_version = models.PositiveIntegerField(null=True, blank=True)
    payment_proof = models.FileField(
        upload_to='registrations/payment_proof/%Y/%m/', storage=CloudinarySignedStorage(),
        validators=[validate_document_file], blank=True, null=True,
    )

    registered_at = models.DateTimeField(auto_now_add=True)
    checked_in = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'player'], name='unique_tournament_registration'),
        ]
        ordering = ['-registered_at']

    def __str__(self):
        return f'{self.player_id} -> {self.tournament_id}'
