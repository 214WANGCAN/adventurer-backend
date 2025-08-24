# uploads/views.py
import uuid, io
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image, ImageOps

# 默认 2MB（你的注释写了5MB，可一并修正）
MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 2 * 1024 * 1024)

def _has_alpha(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA"):
        return True
    if img.mode == "P" and "transparency" in img.info:
        return True
    return False

def _flatten_to_rgb(img: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Flatten RGBA/LA/P(with transparency) to RGB using a solid background."""
    if img.mode in ("RGBA", "LA"):
        alpha = img.split()[-1]
        base = Image.new("RGB", img.size, bg)
        base.paste(img.convert("RGB"), mask=alpha)
        return base
    if img.mode == "P" and "transparency" in img.info:
        return img.convert("RGBA").convert("RGB")
    if img.mode == "P":
        return img.convert("RGB")
    if img.mode != "RGB":
        return img.convert("RGB")
    return img

@csrf_exempt
def upload_image(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('Only POST is allowed')

    f = request.FILES.get('file')
    if not f:
        return HttpResponseBadRequest('Missing file')

    need_compress = f.size > MAX_UPLOAD_SIZE

    try:
        img = Image.open(f)
        img = ImageOps.exif_transpose(img)  # respect camera rotation
    except Exception:
        return HttpResponseBadRequest('Invalid image')

    # Original format/extension (fallback to PNG)
    src_format = (img.format or 'PNG').upper()

    # Decide target format/extension
    # If we need to compress:
    # - PNG/APNG with transparency -> prefer WEBP to keep alpha smaller than PNG
    # - otherwise use JPEG
    if need_compress:
        if _has_alpha(img):
            target_format = "WEBP"
            ext = ".webp"
        else:
            target_format = "JPEG"
            ext = ".jpg"
    else:
        # no compression: keep original bytes/extension
        target_format = src_format
        ext = '.' + src_format.lower()

    # Optional downscale
    if need_compress:
        max_width = 1920
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

    # Prepare bytes
    if need_compress:
        buffer = io.BytesIO()
        if target_format == "JPEG":
            # Ensure no alpha before saving as JPEG (this was the crash)
            img_to_save = _flatten_to_rgb(img)
            img_to_save.save(buffer, format="JPEG", optimize=True, quality=80, progressive=True)
        elif target_format == "WEBP":
            # Keep transparency; quality can be tuned; lossless=True for line art/icons
            # Choose lossless for small icon-like images; heuristic: if very small or few colors.
            lossless = False
            img_to_save = img.convert("RGBA") if _has_alpha(img) else img.convert("RGB")
            img_to_save.save(buffer, format="WEBP", quality=80, method=6, lossless=lossless)
        else:
            # Fallback (rare)
            img.save(buffer, format=target_format, optimize=True)
        buffer.seek(0)
        content = ContentFile(buffer.read())
        filename = f"{uuid.uuid4().hex}{ext}"
    else:
        # No compression: save original stream and keep original extension
        f.seek(0)
        content = ContentFile(f.read())
        filename = f"{uuid.uuid4().hex}{ext}"

    path = f"images/{filename}"
    saved_path = default_storage.save(path, content)
    file_url = settings.MEDIA_URL + saved_path
    absolute_url = request.build_absolute_uri(file_url)

    return JsonResponse({
        "url": absolute_url,
        "compressed": need_compress,
        "format": target_format
    })
