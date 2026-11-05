"""Classic Priest class icon for the Windows desktop shortcut.

The embedded JPEG is the WoW `classicon_priest` game asset. It is included
for application identification only; PriestBot is not affiliated with Blizzard.
Historical icon asset reference: https://www.wowhead.com/classic/class=5/priest
"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

SOURCE_JPEG_B64 = """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"""


def create_priest_icon(root: Path) -> Path:
    """Materialize a multi-resolution .ico in the permanent install directory.

    The icon is generated locally rather than added as a new ZIP member, so
    existing strict ZIP updaters can accept the release unmodified.
    """
    from PIL import Image
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "PriestBot.ico"
    if target.is_file():
        try:
            with Image.open(target) as existing:
                if existing.format == "ICO" and (32, 32) in existing.ico.sizes():
                    return target
        except (ValueError, OSError):
            pass
    with Image.open(BytesIO(base64.b64decode(SOURCE_JPEG_B64))) as original:
        image = original.convert("RGBA").resize((256, 256), Image.Resampling.LANCZOS)
    temp = root / "PriestBot.ico.updating"
    try:
        image.save(temp, format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target
