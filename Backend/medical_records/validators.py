import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


ALLOWED_MEDICAL_DOCUMENT_TYPES = {
    '.pdf': ('application/pdf', (b'%PDF-',)),
    '.jpg': ('image/jpeg', (b'\xff\xd8\xff',)),
    '.jpeg': ('image/jpeg', (b'\xff\xd8\xff',)),
    '.png': ('image/png', (b'\x89PNG\r\n\x1a\n',)),
}


def safe_original_filename(filename):
    return Path(filename or 'document').name.replace('\r', '').replace('\n', '')[:255]


def medical_document_upload_to(instance, filename):
    extension = Path(filename).suffix.lower()
    patient_id = instance.medical_record.patient_id
    return f'medical_documents/{patient_id}/{uuid.uuid4().hex}{extension}'


def validate_medical_document_file(uploaded_file, *, require_declared_mime=False):
    """Validate size, extension, declared MIME and basic binary signature.

    This is intentionally an upload gate, not an antivirus replacement. A
    future malware-scanning integration belongs immediately after this check.
    """
    maximum_size = settings.MEDICAL_DOCUMENT_MAX_SIZE
    if uploaded_file.size > maximum_size:
        raise ValidationError(f'The document must not exceed {maximum_size} bytes.')

    extension = Path(uploaded_file.name).suffix.lower()
    expected = ALLOWED_MEDICAL_DOCUMENT_TYPES.get(extension)
    if expected is None:
        raise ValidationError('Only PDF, JPEG and PNG documents are accepted.')
    expected_mime, signatures = expected
    declared_mime = getattr(uploaded_file, 'content_type', None)
    declared_mime = declared_mime.split(';', 1)[0].lower() if declared_mime else None
    # UploadedFile exposes the client MIME and is checked at the API boundary.
    # Django later reruns validators on FieldFile, which no longer carries it.
    if require_declared_mime and declared_mime is None:
        raise ValidationError('A declared document MIME type is required.')
    if declared_mime is not None and declared_mime != expected_mime:
        raise ValidationError('The declared document MIME type is invalid.')

    position = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else 0
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(position)
    if not any(header.startswith(signature) for signature in signatures):
        raise ValidationError('The document content does not match its declared format.')


def validate_uploaded_medical_document(uploaded_file):
    """Strict boundary validator for a fresh HTTP upload."""
    validate_medical_document_file(uploaded_file, require_declared_mime=True)
