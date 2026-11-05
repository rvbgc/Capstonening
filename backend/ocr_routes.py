import os
import shutil
from io import BytesIO
from threading import BoundedSemaphore

import pytesseract
from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.responses import JSONResponse

router = APIRouter()

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = 6 * 1024 * 1024
MAX_PIXELS = 12_000_000

# Allow one OCR task at a time in this server process.
ocr_slot = BoundedSemaphore(1)

pytesseract.pytesseract.tesseract_cmd = (
    os.getenv("TESSERACT_CMD")
    or shutil.which("tesseract")
    or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


class OCRUploadLimit:
    """Limit the request before FastAPI parses uploaded files."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != "/ocr"
        ):
            await self.app(scope, receive, send)
            return

        body = bytearray()

        while True:
            message = await receive()

            if message["type"] == "http.disconnect":
                return

            chunk = message.get("body", b"")

            if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                response = JSONResponse(
                    {"detail": "Upload request is too large."},
                    status_code=413,
                )
                await response(scope, receive, send)
                return

            body.extend(chunk)

            if not message.get("more_body", False):
                break

        delivered = False

        async def bounded_receive():
            nonlocal delivered

            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": False,
                }

            return await receive()

        await self.app(scope, bounded_receive, send)


@router.post("/ocr")
def extract_screenshot(file: UploadFile = File(...)):
    if not ocr_slot.acquire(blocking=False):
        raise HTTPException(
            429, "OCR is busy. Please try again shortly."
        )

    try:
        raw = file.file.read(MAX_FILE_BYTES + 1)

        if not raw:
            raise HTTPException(400, "The uploaded file is empty.")

        if len(raw) > MAX_FILE_BYTES:
            raise HTTPException(
                413, "Choose an image no larger than 5 MB."
            )

        try:
            with Image.open(BytesIO(raw)) as probe:
                if probe.format not in {"PNG", "JPEG"}:
                    raise HTTPException(
                        415, "Only PNG and JPEG are supported."
                    )

                if probe.width * probe.height > MAX_PIXELS:
                    raise HTTPException(
                        413, "Crop the image to 12 megapixels or less."
                    )

                if getattr(probe, "n_frames", 1) != 1:
                    raise HTTPException(
                        415, "Upload a single, non-animated image."
                    )

                probe.verify()

            with Image.open(BytesIO(raw)) as source:
                source.load()

                with ImageOps.exif_transpose(source).convert("RGBA") as rgba:
                    with Image.new("RGB", rgba.size, "white") as prepared:
                        prepared.paste(rgba, mask=rgba.getchannel("A"))

                        text = pytesseract.image_to_string(
                            prepared,
                            lang="eng",
                            timeout=20,
                        ).strip()

        except Image.DecompressionBombError:
            raise HTTPException(
                413, "The image dimensions are too large."
            )
        except UnidentifiedImageError:
            raise HTTPException(
                415, "This is not a readable PNG or JPEG image."
            )
        except pytesseract.TesseractNotFoundError:
            raise HTTPException(
                503, "The OCR engine is not configured."
            )
        except pytesseract.TesseractError:
            raise HTTPException(
                503, "The OCR engine could not complete the request."
            )
        except RuntimeError:
            raise HTTPException(
                504, "OCR timed out. Try a smaller crop."
            )
        except (OSError, SyntaxError, ValueError):
            raise HTTPException(
                422, "The image could not be processed."
            )

        if not text:
            raise HTTPException(
                422, "No readable text found. Crop or paste the message."
            )

        if len(text) > 5000:
            raise HTTPException(
                422, "Too much text. Crop to one message and retry."
            )

        return {
            "text": text,
            "requires_review": True,
        }

    finally:
        try:
            file.file.close()
        finally:
            ocr_slot.release()