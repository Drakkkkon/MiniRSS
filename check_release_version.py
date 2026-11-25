from __future__ import annotations

import os
import re
import sys
from pathlib import Path

source = Path(__file__).with_name("mini_rss.py").read_text(encoding="utf-8")
match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)', source, re.MULTILINE)
if not match:
    raise SystemExit("APP_VERSION was not found in mini_rss.py")
app_version = match.group(1)
tag = os.environ.get("GITHUB_REF_NAME", "").strip()
tag_version = tag[1:] if tag.lower().startswith("v") else tag
if tag_version != app_version:
    raise SystemExit(f"Release tag {tag!r} does not match APP_VERSION {app_version!r}")
print(f"Release version OK: {app_version}")
