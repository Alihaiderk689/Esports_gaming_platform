from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

DEMO_PASSWORD = 'Demo@12345'

GAMES = [
    {
        'name': 'Valorant',
        'genre': 'Tactical Shooter',
        'platform': 'PC',
        'description': "Riot Games' 5v5 tactical shooter.",
    },
    {
        'name': 'Tekken 8',
        'genre': 'Fighting',
        'platform': 'PC / PS5 / Xbox Series X|S',
        'description': "Bandai Namco's flagship 1v1 fighting game.",
    },
    {
        'name': 'Counter-Strike 2',
        'genre': 'Tactical Shooter',
        'platform': 'PC',
        'description': "Valve's 5v5 tactical shooter, successor to CS:GO.",
    },
    {
        'name': 'PUBG Mobile',
        'genre': 'Battle Royale',
        'platform': 'Mobile',
        'description': 'Squad-based mobile battle royale.',
    },
    {
        'name': 'EA Sports FC',
        'genre': 'Sports',
        'platform': 'PC / PS5 / Xbox Series X|S',
        'description': "EA's football simulation series.",
    },
]

DEMO_PLAYERS = [f'demo.player{i}@espk.test' for i in range(1, 9)]


class Command(BaseCommand):
    help = 'Seeds demo data (games catalog, a demo organizer, demo players, and demo tournaments).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--with-bracket', action='store_true',
            help='Also generate a single-elimination bracket for the demo tournament using real checked-in registrations.',
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            games_by_name = self._seed_games()
            organizer = self._seed_organizer()
            players = self._seed_players()
            tournament = self._seed_tournament(games_by_name['Valorant'], organizer, players)

        if options['with_bracket']:
            self._seed_bracket(tournament)

        self.stdout.write(self.style.SUCCESS('Demo data seeded.'))
        self.stdout.write(f'  Organizer login: demo.organizer@espk.test / {DEMO_PASSWORD}')
        self.stdout.write(f'  Player logins:   demo.player1@espk.test .. demo.player8@espk.test / {DEMO_PASSWORD}')

    def _seed_games(self):
        from games.models import Game

        games_by_name = {}
        for data in GAMES:
            game, created = Game.objects.get_or_create(
                name=data['name'],
                defaults={
                    'genre': data['genre'],
                    'platform': data['platform'],
                    'description': data['description'],
                    'is_active': True,
                },
            )
            games_by_name[data['name']] = game
            self._log(game, created, 'game')
        return games_by_name

    def _seed_organizer(self):
        from core.models import User
        from organizer.models import Organizer

        user, created = User.objects.get_or_create(
            email='demo.organizer@espk.test',
            defaults={
                'first_name': 'Demo',
                'last_name': 'Organizer',
                'is_email_verified': True,
            },
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=['password'])
        self._log(user, created, 'organizer user')

        organizer, created = Organizer.objects.get_or_create(
            user=user,
            defaults={
                'company_name': 'Demo Esports Co.',
                'status': Organizer.Status.APPROVED,
                'last_seen_status': Organizer.Status.APPROVED,
            },
        )
        self._log(organizer, created, 'organizer profile')
        return organizer

    def _seed_players(self):
        from core.models import User

        players = []
        for i, email in enumerate(DEMO_PLAYERS, start=1):
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': 'Demo',
                    'last_name': f'Player{i}',
                    'is_email_verified': True,
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=['password'])
            self._log(user, created, 'player')
            players.append(user)
        return players

    def _seed_tournament(self, game, organizer, players):
        from tourny_regist.models import Registration, Tournament

        now = timezone.now()
        tournament, created = Tournament.objects.get_or_create(
            name='Demo Valorant Showdown',
            defaults={
                'game': game,
                'organizer': organizer,
                'created_by': organizer.user,
                'status': Tournament.Status.APPROVED,
                'is_published': True,
                'mode': Tournament.Mode.ONLINE,
                'bracket_format': Tournament.BracketFormat.SINGLE,
                'team_size': 1,
                'max_participants': len(players),
                'min_participants': 2,
                'is_registration_open': False,
                'starts_at': now + timedelta(days=1),
                'ends_at': now + timedelta(days=2),
                'registration_deadline': now - timedelta(hours=1),
                'contact_organizer_name': 'Demo Organizer',
                'contact_email': organizer.user.email,
            },
        )
        self._log(tournament, created, 'tournament')

        for player in players:
            registration, created = Registration.objects.get_or_create(
                tournament=tournament, player=player,
                defaults={
                    'status': Registration.Status.APPROVED,
                    'checked_in': True,
                    'checked_in_at': now,
                    'full_name': f'{player.first_name} {player.last_name}',
                    'gaming_username': player.email.split('@')[0],
                    'accepted_rules': True,
                    'accepted_code_of_conduct': True,
                },
            )
            self._log(registration, created, 'registration')

        return tournament

    def _seed_bracket(self, tournament):
        from brackets.models import Bracket
        from brackets.services import generate_bracket

        if Bracket.objects.filter(tournament=tournament).exists():
            self.stdout.write(f'  [skip] bracket already exists for {tournament}')
            return
        generate_bracket(tournament)
        self.stdout.write(self.style.SUCCESS(f'  [created] bracket for {tournament}'))

    def _log(self, obj, created, label):
        tag = 'created' if created else 'exists'
        self.stdout.write(f'  [{tag}] {label}: {obj}')
