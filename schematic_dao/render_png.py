#!/usr/bin/env python3
"""render_png — SVG → PNG 转换 (可选, 使用 Playwright)

PFC 资料包提供了 PDF/PNG/SVG 三种规范图. SVG 是真相源,
PNG 通过浏览器渲染获得高保真位图. 此模块封装该转换.

使用前提: pip install playwright && playwright install chromium

若 playwright 不可用, 此函数直接返回 None, 不阻断 pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def svg_to_png(svg_path: Path, png_path: Path,
               width: int = 1800, height: int = 1180,
               scale: int = 2) -> Optional[Path]:
    """通过 Playwright 把 SVG 渲染为 PNG.

    Args:
        svg_path: 源 SVG 文件路径 (file://)
        png_path: 输出 PNG 路径
        width/height: SVG 画布尺寸 (与 SVG 内 width/height 匹配)
        scale: 渲染倍率 (2 = 2x retina)

    Returns:
        png_path 若成功, None 若 playwright 不可用或渲染失败
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    svg_path = Path(svg_path).resolve()
    png_path = Path(png_path).resolve()
    if not svg_path.exists():
        return None

    file_url = svg_path.as_uri()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=scale,
            )
            page = context.new_page()
            page.goto(file_url)
            # 等待 SVG 加载并 layout 完成
            page.wait_for_load_state("networkidle")
            # 截取 SVG 元素本身, 避免周围空白
            svg_el = page.query_selector("svg")
            if svg_el:
                svg_el.screenshot(path=str(png_path), omit_background=False)
            else:
                page.screenshot(path=str(png_path), full_page=True)
            browser.close()
        return png_path
    except Exception as e:
        # 记录但不抛出
        try:
            (png_path.parent / f"{png_path.stem}_render_error.txt").write_text(
                f"PNG 渲染失败: {type(e).__name__}: {e}\n", encoding="utf-8")
        except Exception:
            pass
        return None
