from pathlib import Path

from django.core.files import File

POOL_DIR = Path(__file__).resolve().parent
POOL_FILES = sorted(p for p in POOL_DIR.iterdir() if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))


def assign_next_cover(tournament):
    """Round-robins through the Tekken cover pool, one picture per tournament created."""
    if not POOL_FILES:
        return
    path = POOL_FILES[tournament.pk % len(POOL_FILES)]
    with open(path, 'rb') as f:
        tournament.cover_image.save(path.name, File(f), save=True)
