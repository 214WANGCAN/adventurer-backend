# apps/qrcode_api/views.py
import io
from django.http import HttpResponse, JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import qrcode
from qrcode.constants import ERROR_CORRECT_H


class ComposeQrOnBaseView(APIView):
    """
    GET /api/qr/compose?data=...&label=...&x=100&y=120&size=360&border=0
      - data:   必填，二维码内容（URL/文本）
      - label:  可选，要绘制的文字（>10 字将截断为 10 字并加 ...）
      - x,y:    可选，二维码左上角坐标，默认 (265,560)
      - size:   可选，二维码边长像素，默认 700
      - border: 可选，二维码白边(模块数)，默认 0
    """
    permission_classes = [AllowAny]

    # 固定的文字位置与样式（你可以改成你想要的）
    TEXT_X = 100
    TEXT_Y = 1400
    TEXT_FONT_SIZE = 120
    TEXT_COLOR = (255, 215, 0, 255)  # 纯白

    def _truncate_label(self, s: str, limit: int = 10) -> str:
        s = (s or "").strip()
        if len(s) <= limit:
            return s
        return s[:limit] + "..."

    def _load_font(self, size: int):
        """优先加载项目内字体；失败则回退到 PIL 自带字体"""
        base_dir = Path(__file__).resolve().parent
        font_path = base_dir / "fonts" / "ZiXinFangHuanYeGeTeTi-2.ttf"  # 自行替换文件名
        try:
            if font_path.exists():
                return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            pass
        # 回退：不一定支持中文
        return ImageFont.load_default()

    def get(self, request):
        data = request.query_params.get("data")
        if not data:
            return JsonResponse({"detail": "缺少 data 参数"}, status=400)

        try:
            x = int(request.query_params.get("x", 268))
            y = int(request.query_params.get("y", 565))
            size = int(request.query_params.get("size", 700))
            border = int(request.query_params.get("border", 0))
            download = request.query_params.get("download")  # 任意值即触发下载
        except ValueError:
            return JsonResponse({"detail": "x/y/size/border 必须为整数"}, status=400)

        # 读取底图
        base_dir = Path(__file__).resolve().parent
        base_path = base_dir / "base_images" / "base.png"
        if not base_path.exists():
            return JsonResponse({"detail": f"底图不存在: {base_path}"}, status=500)

        base = Image.open(base_path).convert("RGBA")

        # 生成二维码
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_H,
            box_size=10,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        qr_img = qr_img.resize((size, size), Image.LANCZOS)

        # 合成二维码
        canvas = base.copy()
        if x < 0 or y < 0 or x + size > canvas.width or y + size > canvas.height:
            return JsonResponse({
                "detail": f"二维码区域超出底图范围。底图大小 {canvas.width}x{canvas.height}，"
                          f"请求放置区域 [{x},{y},{x+size},{y+size}]"
            }, status=400)
        canvas.alpha_composite(qr_img, dest=(x, y))

        # ====== 新增：绘制白色文字（居中） ======
        label = request.query_params.get("label", "")
        label = self._truncate_label(label, limit=9)  # 超过 10 字截断加 ...
        if label:
            draw = ImageDraw.Draw(canvas)
            font = self._load_font(self.TEXT_FONT_SIZE)

            # 计算文字宽度并居中
            try:
                text_width = draw.textlength(label, font=font)  # Pillow >=8.0
            except AttributeError:
                text_width, _ = draw.textsize(label, font=font)  # 兼容旧版本

            x = (canvas.width - text_width) // 2
            y = self.TEXT_Y  # 纵向位置仍然写死

            draw.text(
                (x, y),
                label,
                font=font,
                fill=self.TEXT_COLOR,
            )
        # ====== 新增结束 ======


        # 输出 PNG
        buf = io.BytesIO()
        out = canvas.convert("RGBA")
        out.save(buf, format="PNG")
        buf.seek(0)

        resp = HttpResponse(buf.getvalue(), content_type="image/png")
        if download is not None:
            resp["Content-Disposition"] = 'attachment; filename="qr_composed.png"'
        return resp
