from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_SOURCE = ROOT / "mini_rss.py"
EXE_SOURCE = ROOT / "dist" / "MiniRSS.exe"
RELEASE_DIR = ROOT / "release"


def main() -> int:
    # GitHub Actions Windows runners may default to cp1252; keep Russian messages safe.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    if not EXE_SOURCE.exists():
        print("Не найден dist\\MiniRSS.exe. Сначала запустите build_exe.bat.")
        return 1
    source = APP_SOURCE.read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', source, re.MULTILINE)
    if not match:
        print("Не удалось определить APP_VERSION в mini_rss.py.")
        return 1
    version = match.group(1)
    RELEASE_DIR.mkdir(exist_ok=True)
    archive_path = RELEASE_DIR / f"MiniRSS_{version}_win64.zip"
    checksum_path = RELEASE_DIR / f"{archive_path.name}.sha256"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
        archive.write(EXE_SOURCE, arcname="MiniRSS.exe")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="ascii")
    print("Пакет GitHub Release создан:")
    print(f"  {archive_path}")
    print(f"  {checksum_path}")
    print()
    print("Загрузите оба файла в один GitHub Release с тегом v" + version + ".")
    print("MiniRSS найдёт архив и SHA-256 автоматически по GitHub API.")
    print(f"SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
