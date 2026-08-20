"""Tournament lifecycle actions (submit/resubmit/cancel/reschedule/duplicate).

Mirrors brackets/services.py's module-as-service-layer shape: business logic
lives here, not in serializers or views, so both the organizer-facing view
and the admin-approval path can call the exact same functions. Does not
touch brackets/services.py or its lock order — see that module's LOCK ORDER
note if a future stage needs to coordinate a Tournament lock with a Bracket
lock; this module only ever locks the Tournament row.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.audit import log_action
from tourny_regist.emails import send_reschedule_email
from tourny_regist.models import Registration, Team, Tournament
from tourny_regist.validation import validate_tournament_structure

DOCUMENT_FIELDS_REQUIRED_AT_SUBMIT = (
    'company_registration_certificate', 'organizer_cnic_front', 'organizer_cnic_back',
)

COPIED_ON_DUPLICATE = (
    'game', 'mode', 'bracket_format', 'team_size',
    'registration_fee', 'prize_pool',
    'venue_name', 'venue_address', 'venue_map_link', 'venue_city', 'venue_province',
    'venue_country', 'venue_parking_available',
    'discord_server', 'room_id', 'platform', 'game_version', 'server_region',
    'contact_organizer_name', 'contact_company_name', 'contact_phone', 'contact_email',
    'contact_emergency_phone', 'contact_website',
    'social_facebook', 'social_instagram', 'social_discord', 'social_youtube',
)


class NeedsAdminReview(Exception):
    """Raised by cancel_tournament when the tournament has state (registrations
    or a bracket) too significant for a self-service cancel. The view catches
    this and files an AdminReviewRequest instead of letting it become a 500."""


def _lock_tournament(tournament_id):
    return Tournament.objects.select_for_update().get(pk=tournament_id)


def submit_tournament(tournament, actor):
    """DRAFT -> PENDING. Runs the same strictness TournamentApplicationSerializer
    enforces at direct-creation time, against the draft's current saved state."""
    with transaction.atomic():
        tournament = _lock_tournament(tournament.pk)
        if tournament.status != Tournament.Status.DRAFT:
            raise ValidationError({'detail': 'Only a draft tournament can be submitted for approval.'})

        errors = {}
        validate_tournament_structure(lambda f: getattr(tournament, f), errors)
        if not tournament.starts_at:
            errors['starts_at'] = 'Start date is required.'
        elif tournament.starts_at <= timezone.now():
            errors['starts_at'] = 'Tournament start date must be in the future.'
        if tournament.registration_deadline and tournament.registration_deadline <= timezone.now():
            errors['registration_deadline'] = 'Registration deadline must be in the future.'
        for field in DOCUMENT_FIELDS_REQUIRED_AT_SUBMIT:
            if not getattr(tournament, field):
                errors[field] = 'This document is required before submitting for approval.'
        if errors:
            raise ValidationError(errors)

        tournament.status = Tournament.Status.PENDING
        tournament.save(update_fields=['status', 'updated_at'])
        log_action(actor, 'tournament.submitted', tournament)
    return tournament


def resubmit_tournament(tournament, actor):
    """REJECTED -> PENDING, mirroring organizer.views.OrganizerResubmitView's
    pattern for the tournament itself. The organizer is expected to have
    already fixed whatever caused the rejection via the existing PATCH
    endpoint before calling this."""
    with transaction.atomic():
        tournament = _lock_tournament(tournament.pk)
        if tournament.status != Tournament.Status.REJECTED:
            raise ValidationError({'detail': 'Only a rejected tournament can be resubmitted.'})
        tournament.status = Tournament.Status.PENDING
        tournament.rejection_reason = ''
        tournament.save(update_fields=['status', 'rejection_reason', 'updated_at'])
        log_action(actor, 'tournament.resubmitted', tournament)
    return tournament


def _is_safe_to_self_cancel(tournament):
    if Registration.objects.filter(tournament=tournament).exists():
        return False
    if hasattr(tournament, 'bracket'):
        return False
    return True


def cancel_tournament(tournament, actor, reason, *, bypass_safety_check=False):
    """DRAFT/PENDING/APPROVED -> CANCELLED. Safe (no registrations, no
    bracket) cancels immediately. Unsafe raises NeedsAdminReview instead of
    cancelling — the caller must file an AdminReviewRequest and retry this
    same function with bypass_safety_check=True only once an admin has
    approved that request."""
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A cancellation reason is required.'})

    with transaction.atomic():
        tournament = _lock_tournament(tournament.pk)
        if tournament.status == Tournament.Status.CANCELLED:
            raise ValidationError({'detail': 'This tournament is already cancelled.'})
        if tournament.status not in (Tournament.Status.DRAFT, Tournament.Status.PENDING, Tournament.Status.APPROVED):
            raise ValidationError({'detail': f'A tournament in "{tournament.status}" status cannot be cancelled.'})

        if not bypass_safety_check and not _is_safe_to_self_cancel(tournament):
            raise NeedsAdminReview()

        tournament.status = Tournament.Status.CANCELLED
        tournament.cancellation_reason = reason
        tournament.cancelled_by = actor
        tournament.cancelled_at = timezone.now()
        tournament.is_published = False
        tournament.is_registration_open = False
        tournament.save(update_fields=[
            'status', 'cancellation_reason', 'cancelled_by', 'cancelled_at',
            'is_published', 'is_registration_open', 'updated_at',
        ])
        log_action(actor, 'tournament.cancelled', tournament, reason=reason)
    return tournament


def reschedule_tournament(tournament, actor, reason, starts_at, ends_at=None, registration_deadline=None):
    """Updates dates in place but preserves the old values in the audit log
    (AuditLog.metadata) rather than just overwriting them silently. Does not
    introduce a POSTPONED status — this is an audited edit, not a distinct
    lifecycle state. Parameter names match TournamentRescheduleRequestSerializer's
    fields so the view can call this via **serializer.validated_data."""
    new_starts_at, new_ends_at, new_registration_deadline = starts_at, ends_at, registration_deadline
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A reason for rescheduling is required.'})

    errors = {}
    get_field = {
        'mode': None, 'starts_at': new_starts_at, 'ends_at': new_ends_at,
        'registration_deadline': new_registration_deadline,
        'min_participants': None, 'max_participants': None,
    }.get
    # Only the ordering checks apply here (mode/venue fields aren't changing).
    validate_tournament_structure(get_field, errors, require_mode_fields=False)
    if not new_starts_at:
        errors['starts_at'] = 'Start date is required.'
    elif new_starts_at <= timezone.now():
        errors['starts_at'] = 'New start date must be in the future.'
    if errors:
        raise ValidationError(errors)

    with transaction.atomic():
        tournament = _lock_tournament(tournament.pk)
        if tournament.status not in (Tournament.Status.PENDING, Tournament.Status.APPROVED):
            raise ValidationError({'detail': f'A tournament in "{tournament.status}" status cannot be rescheduled.'})

        old_starts_at = tournament.starts_at
        old_ends_at = tournament.ends_at
        old_registration_deadline = tournament.registration_deadline

        tournament.starts_at = new_starts_at
        if new_ends_at is not None:
            tournament.ends_at = new_ends_at
        if new_registration_deadline is not None:
            tournament.registration_deadline = new_registration_deadline
        tournament.save(update_fields=['starts_at', 'ends_at', 'registration_deadline', 'updated_at'])

        log_action(
            actor, 'tournament.rescheduled', tournament, reason=reason,
            old={
                'starts_at': old_starts_at.isoformat() if old_starts_at else None,
                'ends_at': old_ends_at.isoformat() if old_ends_at else None,
                'registration_deadline': old_registration_deadline.isoformat() if old_registration_deadline else None,
            },
            new={
                'starts_at': new_starts_at.isoformat(),
                'ends_at': new_ends_at.isoformat() if new_ends_at else None,
                'registration_deadline': new_registration_deadline.isoformat() if new_registration_deadline else None,
            },
        )

    send_reschedule_email(tournament, old_starts_at, new_starts_at, reason)
    return tournament


def duplicate_tournament(tournament, actor):
    """Creates a new DRAFT copying configuration only — never registrations,
    teams, brackets, matches, champion state, or the compliance documents
    (those are re-required at submit time via submit_tournament)."""
    copied = {field: getattr(tournament, field) for field in COPIED_ON_DUPLICATE}
    new_tournament = Tournament.objects.create(
        name=f'{tournament.name} (Copy)',
        organizer=tournament.organizer,
        created_by=actor,
        status=Tournament.Status.DRAFT,
        is_published=False,
        **copied,
    )
    log_action(actor, 'tournament.duplicated', new_tournament, source_tournament_id=tournament.pk)
    return new_tournament


def _is_safe_to_cancel_registration(registration):
    # brackets.Match is imported locally rather than at module level: tourny_regist
    # doesn't otherwise depend on brackets (brackets depends on tourny_regist, not
    # the reverse), and this keeps that the only place the dependency shows up,
    # mirroring how dashboard/views.py already reads across both apps read-only.
    from brackets.models import Match

    if not hasattr(registration.tournament, 'bracket'):
        return True
    has_played = Match.objects.filter(
        tournament=registration.tournament, status=Match.Status.COMPLETED,
    ).filter(Q(player1=registration.player) | Q(player2=registration.player)).exists()
    return not has_played


def cancel_registration(registration, actor, reason, *, bypass_safety_check=False):
    """APPROVED/PENDING -> CANCELLED, immediately if safe (no bracket yet, or
    the player hasn't actually played a match) — otherwise raises
    NeedsAdminReview so the caller can file an AdminReviewRequest instead.
    A soft-cancel (status transition), not the hard delete
    RegistrationDeleteView still uses for a player's own self-withdrawal.

    No payment gateway/ledger exists in this codebase (payment_proof is just
    an uploaded receipt, not a processed transaction) — so this deliberately
    does not attempt to auto-refund. If the registration's fee was paid, that
    fact stays visible via tournament.registration_fee + the audit trail for
    manual reconciliation, rather than this function inventing a fake refund
    step that doesn't correspond to any real money movement."""
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A cancellation reason is required.'})

    with transaction.atomic():
        registration = Registration.objects.select_for_update().get(pk=registration.pk)
        if registration.status in (Registration.Status.CANCELLED, Registration.Status.DISQUALIFIED):
            raise ValidationError({'detail': f'This registration is already {registration.status}.'})

        if not bypass_safety_check and not _is_safe_to_cancel_registration(registration):
            raise NeedsAdminReview()

        registration.status = Registration.Status.CANCELLED
        registration.cancellation_reason = reason
        registration.cancelled_by = actor
        registration.cancelled_at = timezone.now()
        registration.checked_in = False
        registration.save(update_fields=[
            'status', 'cancellation_reason', 'cancelled_by', 'cancelled_at', 'checked_in',
        ])
        log_action(actor, 'registration.cancelled', registration, reason=reason)
    return registration


def disqualify_registration(registration, actor, reason):
    """Marks a participant DISQUALIFIED, then — if a bracket already exists —
    auto-forfeits any match they're currently READY to play, so a disqualified
    player never sits waiting in a match nobody can complete. The bracket-side
    forfeit runs after the registration transaction commits, as its own
    separately-locked, separately-atomic call into brackets.services (which
    takes the Tournament/Match locks per that module's own LOCK ORDER) —
    keeping the two operations decoupled means never having to reason about
    interleaving a Registration lock with that ordering at all."""
    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A disqualification reason is required.'})

    with transaction.atomic():
        registration = Registration.objects.select_for_update().get(pk=registration.pk)
        if registration.status == Registration.Status.DISQUALIFIED:
            raise ValidationError({'detail': 'This registration is already disqualified.'})
        registration.status = Registration.Status.DISQUALIFIED
        registration.disqualification_reason = reason
        registration.disqualified_by = actor
        registration.disqualified_at = timezone.now()
        registration.checked_in = False
        registration.save(update_fields=[
            'status', 'disqualification_reason', 'disqualified_by', 'disqualified_at', 'checked_in',
        ])
        log_action(actor, 'registration.disqualified', registration, reason=reason)

    if hasattr(registration.tournament, 'bracket'):
        from brackets.services import disqualify_player_from_bracket
        disqualify_player_from_bracket(registration.tournament, registration.player, actor, reason)

    return registration


def lock_team_roster(team, actor):
    """Organizer self-service — locking only ever restricts future roster
    changes, so it carries none of cancel_tournament's need for an admin-
    review escalation path."""
    with transaction.atomic():
        team = Team.objects.select_for_update().get(pk=team.pk)
        if team.is_locked:
            raise ValidationError({'detail': 'This roster is already locked.'})
        team.is_locked = True
        team.locked_at = timezone.now()
        team.locked_by = actor
        team.save(update_fields=['is_locked', 'locked_at', 'locked_by'])
        log_action(actor, 'team.roster_locked', team)
    return team


def unlock_team_roster(team, actor):
    """Staff-only (enforced by the view, not here) — see Team.is_locked's
    docstring for why re-opening a locked roster is treated as exceptional."""
    with transaction.atomic():
        team = Team.objects.select_for_update().get(pk=team.pk)
        if not team.is_locked:
            raise ValidationError({'detail': 'This roster is not locked.'})
        team.is_locked = False
        team.locked_at = None
        team.locked_by = None
        team.save(update_fields=['is_locked', 'locked_at', 'locked_by'])
        log_action(actor, 'team.roster_unlocked', team)
    return team


def substitute_team_member(team, actor, outgoing_player, incoming_player, reason):
    """Staff-only (enforced by the view) swap of one roster member for
    another on an already-locked team — this is the "exceptional workflow"
    substitution path; ordinary pre-lock roster changes go through
    TeamJoinView/TeamLeaveView instead. Does not touch historical match
    participants — Match.player1/player2 already point at the specific User
    who actually played, so swapping the roster here can't retroactively
    change who competed in a completed match."""
    from tourny_regist.models import TeamMembership

    if not reason or not reason.strip():
        raise ValidationError({'reason': 'A reason for the substitution is required.'})

    with transaction.atomic():
        team = Team.objects.select_for_update().get(pk=team.pk)
        if not team.is_locked:
            raise ValidationError({'detail': 'Only a locked roster can have a substitution made.'})
        membership = TeamMembership.objects.filter(team=team, player=outgoing_player).first()
        if membership is None:
            raise ValidationError({'detail': 'That player is not on this roster.'})
        if TeamMembership.objects.filter(team=team, player=incoming_player).exists():
            raise ValidationError({'detail': 'That player is already on this roster.'})

        membership.delete()
        TeamMembership.objects.create(team=team, player=incoming_player)
        log_action(
            actor, 'team.member_substituted', team, reason=reason,
            outgoing_player_id=outgoing_player.pk, incoming_player_id=incoming_player.pk,
        )
    return team
