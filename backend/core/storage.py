import logging
from urllib.parse import quote

import cloudinary.api
import cloudinary.exceptions
import cloudinary.uploader
from django.core import signing
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class StorageUnavailable(APIException):
    """Raised (as a DRF APIException, even though this is plain Django Storage
    code) when Cloudinary itself fails — rate limited, quota exceeded, network
    error. Every upload in the app (organizer CNIC/company docs, tournament
    compliance documents, payment proofs) goes through this one class, so
    fixing it here is the single place that gives all of them a clean 503
    instead of an unhandled 500, rather than patching every view separately."""

    status_code = 503
    default_detail = 'File storage is temporarily unavailable. Please try again in a moment.'
    default_code = 'storage_unavailable'


@deconstructible
class CloudinarySignedStorage(Storage):
    """Stores sensitive uploads (CNIC scans, payment proofs, compliance
    documents) in Cloudinary rather than local disk — local disk gets wiped on
    every deploy/restart on most hosting platforms, Cloudinary doesn't.

    Files are uploaded as Cloudinary "authenticated" resources, which
    Cloudinary itself refuses to serve without a valid signature (verified
    live: the same asset 200s with a correctly signed URL and 401s without
    one). `.url()` never returns that Cloudinary URL directly — it returns our
    own short-lived signed link instead (served by core.views.secure_media_view,
    which mints a fresh signed Cloudinary URL only after checking it). That
    keeps the access-control story identical to before this migration: the
    only way to get a working link at all is through an API call that already
    passed its own ownership/staff check.
    """

    signer_salt = 'secure-media'
    url_max_age = 600  # seconds our own link stays valid
    resource_type = 'raw'
    delivery_type = 'authenticated'

    def _open(self, name, mode='rb'):
        raise NotImplementedError('Cloudinary-backed files are fetched via .url(), not opened directly.')

    def _save(self, name, content):
        content.seek(0)
        try:
            result = cloudinary.uploader.upload(
                content.read(),
                public_id=name,
                resource_type=self.resource_type,
                type=self.delivery_type,
                overwrite=True,
                unique_filename=False,
                use_filename=False,
            )
        except Exception:
            logger.exception('Cloudinary upload failed for %s', name)
            raise StorageUnavailable()
        return result['public_id']

    def exists(self, name):
        try:
            cloudinary.api.resource(name, resource_type=self.resource_type, type=self.delivery_type)
            return True
        except cloudinary.exceptions.NotFound:
            return False
        except Exception:
            logger.exception('Cloudinary existence check failed for %s', name)
            raise StorageUnavailable()

    def delete(self, name):
        try:
            cloudinary.uploader.destroy(name, resource_type=self.resource_type, type=self.delivery_type)
        except Exception:
            logger.exception('Cloudinary delete failed for %s', name)
            raise StorageUnavailable()

    def size(self, name):
        return cloudinary.api.resource(name, resource_type=self.resource_type, type=self.delivery_type)['bytes']

    def get_accessed_time(self, name):
        raise NotImplementedError('Cloudinary does not track last-accessed time.')

    def get_created_time(self, name):
        info = cloudinary.api.resource(name, resource_type=self.resource_type, type=self.delivery_type)
        return info['created_at']

    def get_modified_time(self, name):
        return self.get_created_time(name)

    def url(self, name):
        token = signing.TimestampSigner(salt=self.signer_salt).sign(name)
        return f'/secure-media/?token={quote(token)}'
