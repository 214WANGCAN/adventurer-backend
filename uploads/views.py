# uploads/views.py
import uuid, io
from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from PIL import Image

MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 2 * 1024 * 1024)  # 默认5MB

@csrf_exempt
def upload_image(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('Only POST is allowed')

    f = request.FILES.get('file')
    if not f:
        return HttpResponseBadRequest('Missing file')

    # 判断是否需要压缩
    need_compress = f.size > MAX_UPLOAD_SIZE

    try:
        img = Image.open(f)
    except Exception:
        return HttpResponseBadRequest('Invalid image')

    # 决定文件扩展名和格式
    format = img.format or 'PNG'
    ext = '.' + format.lower()
    filename = f"{uuid.uuid4().hex}{ext}"

    if need_compress:
        # 压缩逻辑
        # 1. 如果是 PNG，可以转为 JPEG/WebP（体积更小）
        if format.upper() == "PNG":
            format = "JPEG"
            ext = ".jpg"
            filename = f"{uuid.uuid4().hex}{ext}"

        # 2. 调整尺寸（可选）和质量
        max_width = 1920
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format=format, optimize=True, quality=80)  # quality 0-100
        buffer.seek(0)
        content = ContentFile(buffer.read())
    else:
        # 不压缩，直接保存
        f.seek(0)
        content = ContentFile(f.read())

    path = f"images/{filename}"
    saved_path = default_storage.save(path, content)
    file_url = settings.MEDIA_URL + saved_path
    absolute_url = request.build_absolute_uri(file_url)

    return JsonResponse({"url": absolute_url, "compressed": need_compress})
