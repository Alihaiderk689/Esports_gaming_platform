import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import PendingRegistration

logger = logging.getLogger(__name__)

#: A signup that never verifies within a week is abandoned, not "still in
#: progress" - the OTP itself already expires after 10 minutes (core/otp.py),
#: so this is a much longer, deliberately generous window before the row (and
#: any CNIC/company document already pushed to Cloudinary for an organizer
#: signup) is actually deleted.
DEFAULT_RETENTION_DAYS = 7

#: Cloudinary-backed FileFields on PendingRegistration whose storage object
#: also needs to be deleted, not just the row - see core/storage.py's
#: CloudinarySignedStorage. Kept as a tuple here rather than introspecting the
#: model's fields so a future non-Cloudinary field added to this model isn't
#: silently swept into this list.
_CLOUDINARY_DOCUMENT_FIELDS = ('cnic_document', 'company_document')


class Command(BaseCommand):
    help = (
        "Deletes PendingRegistration rows (email-OTP signups that were never "
        "verified) older than --older-than-days, along with any CNIC/company "
        "document already uploaded to Cloudinary for an abandoned organizer "
        "signup. Intended to run on a schedule (e.g. a Render Cron Job) - see "
        "docs/SECURITY_CHECKLIST.md's Scheduled cleanup section for the "
        "equivalent pattern already used for flushexpiredtokens; this command "
        "is meant to be scheduled alongside it, not instead of it."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--older-than-days', type=int, default=DEFAULT_RETENTION_DAYS,
            help=f'Delete pending registrations created more than this many days ago (default: {DEFAULT_RETENTION_DAYS}).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be deleted without deleting anything.',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=options['older_than_days'])
        stale_ids = list(
            PendingRegistration.objects.filter(created_at__lt=cutoff).values_list('pk', flat=True),
        )

        if options['dry_run']:
            self.stdout.write(
                f'{len(stale_ids)} pending registration(s) would be deleted '
                f'(created before {cutoff.isoformat()}).',
            )
            return

        deleted_rows = 0
        deleted_documents = 0
        # Re-fetched one at a time by pk, rather than iterating the queryset
        # while deleting from it, so this can't interact badly with deleting
        # the very rows the query is reading.
        for pk in stale_ids:
            pending = PendingRegistration.objects.filter(pk=pk).first()
            if pending is None:
                continue

            for field_name in _CLOUDINARY_DOCUMENT_FIELDS:
                field_file = getattr(pending, field_name)
                if not field_file:
                    continue
                try:
                    field_file.delete(save=False)
                    deleted_documents += 1
                except Exception:
                    # A Cloudinary delete failure for one abandoned signup's
                    # document must not stop the rest of the cleanup run -
                    # same "one bad recipient doesn't break the whole batch"
                    # principle as tourny_regist/emails.py's announcement
                    # send loop. The row itself is still deleted below; the
                    # orphaned Cloudinary asset (if the delete call actually
                    # failed rather than the asset already being gone) is
                    # logged for manual follow-up rather than silently lost.
                    logger.exception(
                        'Failed to delete Cloudinary document %s for expired PendingRegistration %s',
                        field_name, pk,
                    )

            pending.delete()
            deleted_rows += 1

        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted_rows} expired pending registration(s) and '
            f'{deleted_documents} associated Cloudinary document(s).',
        ))
