"""生成 Nini 绿色 N 图标的 .ico 文件。

设计与 web/src/components/GlobalNav.tsx 中的 NiniLogo 保持一致：
- 32x32 画布，圆角矩形背景
- 渐变：#1FD8C3 → #0A8B7E（左上到右下）
- 白色 N 字母 + 4 个节点圆点
"""

from PIL import Image, ImageDraw
import struct
import io
import os


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """线性插值两个颜色。"""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, bbox: list[float], radius: int, fill: tuple[int, int, int]) -> None:
    """绘制圆角矩形。"""
    x1, y1, x2, y2 = bbox
    # 四个圆角
    draw.ellipse([x1, y1, x1 + 2 * radius, y1 + 2 * radius], fill=fill)
    draw.ellipse([x2 - 2 * radius, y1, x2, y1 + 2 * radius], fill=fill)
    draw.ellipse([x1, y2 - 2 * radius, x1 + 2 * radius, y2], fill=fill)
    draw.ellipse([x2 - 2 * radius, y2 - 2 * radius, x2, y2], fill=fill)
    # 中间矩形
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)


def _draw_circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill: tuple[int, int, int]) -> None:
    """绘制圆形。"""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def _draw_line(draw: ImageDraw.ImageDraw, x1: float, y1: float, x2: float, y2: float,
               width: float, fill: tuple[int, int, int]) -> None:
    """绘制带圆角端点的线条。"""
    draw.line([(x1, y1), (x2, y2)], fill=fill, width=int(width))
    # 圆角端点
    r = width / 2
    _draw_circle(draw, x1, y1, r, fill)
    _draw_circle(draw, x2, y2, r, fill)


def create_nini_icon(size: int = 256) -> Image.Image:
    """创建 Nini 绿色 N 图标。"""
    # 创建带透明通道的图像
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 缩放因子
    scale = size / 32

    # 渐变色
    color_top_left = (0x1F, 0xD8, 0xC3)  # #1FD8C3
    color_bottom_right = (0x0A, 0x8B, 0x7E)  # #0A8B7E

    # 绘制渐变背景（逐行像素着色实现渐变）
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            color = _lerp_color(color_top_left, color_bottom_right, t)
            img.putpixel((x, y), color + (255,))

    # 绘制圆角矩形（覆盖渐变背景）
    corner_radius = int(9 * scale)
    # 用蒙版实现圆角
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    _draw_rounded_rect(mask_draw, [0, 0, size - 1, size - 1], corner_radius, 255)
    img.putalpha(mask)

    # 重新绘制渐变（带圆角）
    for y in range(size):
        for x in range(size):
            if mask.getpixel((x, y)) > 0:
                t = (x + y) / (2 * size)
                color = _lerp_color(color_top_left, color_bottom_right, t)
                img.putpixel((x, y), color + (255,))

    draw = ImageDraw.Draw(img)

    # N 字母参数
    white = (255, 255, 255)
    white_node = (255, 255, 255, 242)  # fillOpacity=0.95 → 0.95*255≈242

    line_width = 2.4 * scale
    # N 的三个点坐标
    p1 = (8.5 * scale, 8.5 * scale)   # 左上
    p2 = (8.5 * scale, 23.5 * scale)  # 左下
    p3 = (23.5 * scale, 8.5 * scale)  # 右上
    p4 = (23.5 * scale, 23.5 * scale) # 右下

    # 绘制 N 的三条线
    _draw_line(draw, *p1, *p2, line_width, white)  # 左竖线
    _draw_line(draw, *p1, *p4, line_width, white)  # 对角线
    _draw_line(draw, *p3, *p4, line_width, white)  # 右竖线

    # 绘制 4 个节点圆点
    node_radius = 2.2 * scale
    for point in [p1, p2, p3, p4]:
        _draw_circle(draw, *point, node_radius, white_node)

    return img


def save_as_ico(img: Image.Image, output_path: str) -> None:
    """保存为 .ico 格式（多尺寸）。"""
    # Windows 图标标准尺寸
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    for s in sizes:
        resized = img.resize((s, s), Image.Resampling.LANCZOS)
        images.append(resized)

    # 保存为 ICO
    images[0].save(
        output_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )


if __name__ == '__main__':
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, 'nini.ico')

    print("生成 Nini 绿色 N 图标...")
    icon = create_nini_icon(256)
    save_as_ico(icon, output_path)
    print(f"已保存到: {output_path}")
