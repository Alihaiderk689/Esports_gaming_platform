from tourny_regist.models import Tournament


def validate_tournament_structure(get_field, errors, *, require_mode_fields=True):
    """Field-ordering/mode-conditional checks shared by tournament creation,
    editing, and draft submission (see TournamentApplicationSerializer,
    TournamentUpdateSerializer, tourny_regist.lifecycle.submit_tournament).

    `get_field(name)` returns the effective value for that field name — a
    dict.get for a full payload, or a "use incoming attrs, else fall back to
    the saved instance" closure for a partial update. `errors` is mutated in
    place with the same field-keyed messages these validate() methods have
    always raised. `require_mode_fields=False` skips the venue/platform
    "required for this mode" checks — used when editing a still-incomplete
    DRAFT, where those fields may legitimately be blank."""
    mode = get_field('mode')
    if require_mode_fields:
        if mode != Tournament.Mode.ONLINE:
            for field in ('venue_name', 'venue_address', 'venue_city', 'venue_country'):
                if not get_field(field):
                    errors[field] = 'This field is required for offline/hybrid tournaments.'
        if mode != Tournament.Mode.OFFLINE:
            if not get_field('platform'):
                errors['platform'] = 'This field is required for online/hybrid tournaments.'

    starts_at = get_field('starts_at')
    ends_at = get_field('ends_at')
    registration_deadline = get_field('registration_deadline')
    min_participants = get_field('min_participants')
    max_participants = get_field('max_participants')

    if starts_at and ends_at and ends_at < starts_at:
        errors['ends_at'] = 'End date must be on or after the start date.'
    if starts_at and registration_deadline and registration_deadline > starts_at:
        errors['registration_deadline'] = 'Registration deadline must be before the tournament starts.'
    if min_participants and max_participants and min_participants > max_participants:
        errors['min_participants'] = 'Minimum participants cannot exceed maximum participants.'
