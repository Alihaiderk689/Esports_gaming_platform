from pathlib import Path

from django.core.files import File

BANNERS_DIR = Path(__file__).resolve().parent


def assign_game_banner(tournament):
    """Sets the tournament's cover to its game's dedicated banner image, if we have one."""
    path = BANNERS_DIR / f'{tournament.game.slug}.jpg'
    if not path.exists():
        return
    with open(path, 'rb') as f:
        tournament.cover_image.save(path.name, File(f), save=True)
