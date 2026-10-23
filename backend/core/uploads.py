"""Gestione sicura dei file caricati (fatture, ricevute spese).

- i file vengono salvati con un nome casuale, non indovinabile;
- sono ammessi solo PDF e immagini JPEG/PNG, verificati anche dal contenuto;
- il download passa sempre da una vista autenticata (vedi ``protected_file_response``).
"""

import mimetypes
import os
import uuid
from pathlib import PurePosixPath
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from django.utils.deconstruct import deconstructible


MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # nginx accetta fino a 25 MB

# estensione -> firme (magic bytes) ammesse all'inizio del file
ALLOWED_SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


@deconstructible
class RandomUploadPath:
    """Salva il file come ``<prefisso>/<anno>/<mese>/<uuid><estensione>``."""

    def __init__(self, prefix):
        self.prefix = prefix

    def __call__(self, instance, filename):
        extension = os.path.splitext(filename)[1].lower()
        if extension not in ALLOWED_SIGNATURES:
            extension = ""
        now = timezone.now()
        return f"{self.prefix}/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"

    def __eq__(self, other):
        return isinstance(other, RandomUploadPath) and other.prefix == self.prefix


def validate_uploaded_file(uploaded_file):
    """Accetta solo PDF/JPEG/PNG reali e non troppo grandi."""
    if uploaded_file is None:
        raise ValidationError("Allega un file.")
    name = getattr(uploaded_file, "name", "") or ""
    extension = os.path.splitext(name)[1].lower()
    if extension not in ALLOWED_SIGNATURES:
        raise ValidationError("Formato non supportato: carica un PDF, JPG o PNG.")
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_UPLOAD_SIZE:
        raise ValidationError("Il file supera la dimensione massima di 20 MB.")
    if size == 0:
        raise ValidationError("Il file è vuoto.")
    # Se il file è già salvato (FieldFile) non rileggiamo il contenuto.
    if getattr(uploaded_file, "_committed", False):
        return
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(16)
    finally:
        uploaded_file.seek(position)
    if isinstance(header, str):
        header = header.encode("latin-1", errors="ignore")
    if not any(header.startswith(signature) for signature in ALLOWED_SIGNATURES[extension]):
        raise ValidationError("Il contenuto del file non corrisponde a un PDF, JPG o PNG valido.")


def protected_file_response(field_file, download_name=""):
    """Restituisce il file solo a chi ha superato i controlli della vista.

    In produzione delega l'invio a nginx tramite ``X-Accel-Redirect`` verso una
    location ``internal``; in sviluppo il file viene servito direttamente.
    """
    if not field_file or not field_file.name:
        raise Http404("File non disponibile.")
    relative = PurePosixPath(field_file.name)
    if relative.is_absolute() or ".." in relative.parts:
        raise Http404("File non disponibile.")
    filename = download_name or relative.name
    content_type = mimetypes.guess_type(filename)[0] or mimetypes.guess_type(relative.name)[0] or "application/octet-stream"
    disposition = f"inline; filename*=UTF-8''{quote(filename)}"

    if getattr(settings, "MEDIA_USE_X_ACCEL_REDIRECT", False):
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = f"{settings.MEDIA_X_ACCEL_PREFIX.rstrip('/')}/{quote(str(relative))}"
    else:
        try:
            handle = field_file.storage.open(field_file.name, "rb")
        except (FileNotFoundError, OSError) as exc:
            raise Http404("File non disponibile.") from exc
        response = FileResponse(handle, content_type=content_type)
    response["Content-Disposition"] = disposition
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
