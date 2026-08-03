import logging

from django.conf import settings
from django.core.mail import send_mail

from tourny_regist.models import Registration, TeamMembership

logger = logging.getLogger(__name__)


def _registered_players(tournament):
    """Every player actually part of an approved registration for this tournament —
    the solo registrant, or every member of a registered team (only the captain
    gets their own Registration row for team-based tournaments, so team members
    have to be pulled in separately via TeamMembership)."""
    registrations = Registration.objects.filter(
        tournament=tournament, status=Registration.Status.APPROVED,
    ).select_related('player')

    players = {}
    team_ids = []
    for registration in registrations:
        if registration.team_id:
            team_ids.append(registration.team_id)
        else:
            players[registration.player_id] = registration.player

    if team_ids:
        memberships = TeamMembership.objects.filter(team_id__in=team_ids).select_related('player')
        for membership in memberships:
            players[membership.player_id] = membership.player

    return list(players.values())


def send_announcement_emails(tournament, announcement):
    """Notify every registered player when an organizer posts a new tournament
    announcement, so players who aren't actively watching the tournament page
    still find out about timing/venue/rule changes. Never raises — a failure
    here (bad SMTP creds, one bad address) must not turn a successful
    announcement post into an error response, since the announcement itself
    is already saved by the time this runs."""
    try:
        players = _registered_players(tournament)
    except Exception:
        logger.exception('Failed to look up registered players for tournament %s', tournament.pk)
        return

    link = f'{settings.FRONTEND_URL}/tournaments/{tournament.pk}'
    for player in players:
        try:
            send_mail(
                subject=f'[{tournament.name}] {announcement.title}',
                message=(
                    f'{announcement.message}\n\n'
                    f'— New announcement from the organizers of {tournament.name}.\n'
                    f'View the tournament: {link}'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[player.email],
            )
        except Exception:
            logger.exception(
                'Failed to send announcement email to user %s for tournament %s',
                player.pk, tournament.pk,
            )


def send_tournament_win_email(tournament, champion):
    """Congratulate the champion by email once brackets.services.finalize_tournament_champion
    has decided the tournament. Never raises, same reasoning as send_announcement_emails —
    the win is already persisted on the Tournament by the time this runs, so an SMTP
    failure here must not surface as an error anywhere."""
    link = f'{settings.FRONTEND_URL}/dashboard'
    prize_line = (
        f"You've also won a prize pool of PKR {tournament.prize_pool:,.0f}.\n\n"
        if tournament.prize_pool else ''
    )
    try:
        send_mail(
            subject=f'🏆 You won {tournament.name}!',
            message=(
                f'Congratulations, {champion.first_name or champion.email}!\n\n'
                f'You are the champion of {tournament.name}. {prize_line}'
                f'Log in to your dashboard to see it: {link}'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[champion.email],
        )
    except Exception:
        logger.exception(
            'Failed to send tournament-win email to user %s for tournament %s',
            champion.pk, tournament.pk,
        )
