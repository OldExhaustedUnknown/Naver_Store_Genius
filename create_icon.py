# -*- coding: utf-8 -*-
"""앱 아이콘 생성 — 네이버 스마트스토어 브랜드 컬러"""

from PIL import Image, ImageDraw


def create_app_icon(output_path: str = "app_icon.ico"):
    """256x256 네이버 그린 테마 아이콘"""
    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    NAVER_GREEN = (3, 199, 90)       # #03C75A
    NAVER_GREEN_DARK = (0, 148, 45)  # #00942D
    WHITE = (255, 255, 255)

    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        s = size / 256
        margin = int(8 * s)

        # 배경: 둥근 사각형 — 네이버 그린
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=int(48 * s),
            fill=NAVER_GREEN,
        )
        # 하단 그라디언트
        draw.rounded_rectangle(
            [margin, int(size * 0.55), size - margin, size - margin],
            radius=int(48 * s),
            fill=NAVER_GREEN_DARK,
        )
        draw.rounded_rectangle(
            [margin, margin, size - margin, int(size * 0.6)],
            radius=int(48 * s),
            fill=NAVER_GREEN,
        )

        # 쇼핑백
        cx, cy = size // 2, int(size * 0.48)
        bag_w, bag_h = int(100 * s), int(95 * s)
        bag_left = cx - bag_w // 2
        bag_top = cy - bag_h // 2 + int(15 * s)
        bag_right = cx + bag_w // 2
        bag_bottom = cy + bag_h // 2 + int(15 * s)

        draw.rounded_rectangle(
            [bag_left, bag_top, bag_right, bag_bottom],
            radius=int(12 * s), fill=WHITE,
        )

        # 손잡이
        draw.arc(
            [cx - int(40 * s), bag_top - int(35 * s), cx + int(40 * s), bag_top + int(35 * s)],
            start=180, end=0, fill=WHITE, width=max(2, int(6 * s)),
        )

        # 번개 — 네이버 그린
        bolt_top = bag_top + int(15 * s)
        if size >= 32:
            bolt_points = [
                (cx + int(5 * s), bolt_top),
                (cx - int(12 * s), bolt_top + int(30 * s)),
                (cx + int(2 * s), bolt_top + int(28 * s)),
                (cx - int(5 * s), bolt_top + int(55 * s)),
                (cx + int(18 * s), bolt_top + int(22 * s)),
                (cx + int(2 * s), bolt_top + int(24 * s)),
            ]
            draw.polygon(bolt_points, fill=NAVER_GREEN)

        # 시계 뱃지 — 오렌지 (네이버 warning 색)
        badge_r = int(38 * s)
        bcx = size - margin - badge_r - int(5 * s)
        bcy = size - margin - badge_r - int(5 * s)

        draw.ellipse(
            [bcx - badge_r, bcy - badge_r, bcx + badge_r, bcy + badge_r],
            fill=(255, 114, 0), outline=WHITE, width=max(1, int(3 * s)),
        )

        if size >= 48:
            clock_r = int(22 * s)
            draw.ellipse(
                [bcx - clock_r, bcy - clock_r, bcx + clock_r, bcy + clock_r],
                outline=WHITE, width=max(1, int(2 * s)),
            )
            draw.line([(bcx, bcy), (bcx, bcy - int(14 * s))], fill=WHITE, width=max(1, int(3 * s)))
            draw.line([(bcx, bcy), (bcx + int(12 * s), bcy)], fill=WHITE, width=max(1, int(2 * s)))
            dot_r = max(1, int(3 * s))
            draw.ellipse([bcx - dot_r, bcy - dot_r, bcx + dot_r, bcy + dot_r], fill=WHITE)

        images.append(img)

    images[0].save(output_path, format="ICO", sizes=[(sz, sz) for sz in sizes], append_images=images[1:])
    images[0].save(output_path.replace(".ico", ".png"), format="PNG")
    print(f"아이콘 생성: {output_path}")


if __name__ == "__main__":
    create_app_icon()
