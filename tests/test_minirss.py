from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import mini_rss  # noqa: E402
import create_update_package  # noqa: E402


class FakeResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class FeedTests(unittest.TestCase):
    def test_parse_rss_feed(self):
        payload = b"""<?xml version='1.0'?><rss version='2.0'><channel><title>Sample</title>
        <item><title>Hello</title><link>https://example.com/hello</link>
        <description>World</description><pubDate>Tue, 25 Nov 2026 10:00:00 GMT</pubDate></item>
        </channel></rss>"""
        title, items = mini_rss.parse_feed(payload)
        self.assertEqual(title, "Sample")
        self.assertEqual(items[0]["title"], "Hello")
        self.assertEqual(items[0]["summary"], "World")
        self.assertTrue(items[0]["timestamp"] > 0)

    def test_parse_atom_feed(self):
        payload = b"""<feed xmlns='http://www.w3.org/2005/Atom'><title>Atom sample</title>
        <entry><title>Atom news</title><link href='https://example.com/a'/><summary>Details</summary></entry>
        </feed>"""
        title, items = mini_rss.parse_feed(payload)
        self.assertEqual(title, "Atom sample")
        self.assertEqual(items[0]["link"], "https://example.com/a")


class ThemeAndPresetTests(unittest.TestCase):
    def test_liquid_glass_theme_is_separate_from_existing_themes(self):
        self.assertIn("iOS 27 · Liquid Glass", mini_rss.THEMES)
        self.assertEqual(mini_rss.THEMES["Светлая"]["bg"], "#f3f5fa")
        self.assertEqual(mini_rss.THEMES["Тёмная"]["bg"], "#191d25")

    def test_liquid_glass_has_icon_material_palette(self):
        palette = mini_rss.THEMES["iOS 27 · Liquid Glass"]
        self.assertTrue(palette["glass_highlight"])
        self.assertTrue(palette["glass_edge"])
        self.assertTrue(palette["glass_shadow"])
        self.assertIn("settings", mini_rss.GLYPHS)
        self.assertIn("favorite_filled", mini_rss.GLYPHS)

    def test_glass_dark_palette_contains_required_surface_colors(self):
        self.assertIn("bg", mini_rss.GLASS_DARK_THEME)
        self.assertIn("glass", mini_rss.GLASS_DARK_THEME)
        self.assertIn("glass_edge", mini_rss.GLASS_DARK_THEME)
        self.assertIn("glass_highlight", mini_rss.GLASS_DARK_THEME)
        self.assertEqual(mini_rss.APP_VERSION, "1.4.4")

    def test_requested_technology_sources_are_presets(self):
        by_title = {feed["title"]: feed["url"] for feed in mini_rss.PRESET_FEEDS}
        self.assertIn("Rozetked · Google Новости", by_title)
        self.assertIn("iGuides · Google Новости", by_title)
        self.assertEqual(by_title["4PDA"], "https://4pda.to/feed/")


class GithubUpdateTests(unittest.TestCase):
    def test_normalize_repo(self):
        self.assertEqual(mini_rss.normalize_github_repo("https://github.com/owner/project/"), "owner/project")
        with self.assertRaises(ValueError):
            mini_rss.normalize_github_repo("owner/project/extra")

    def test_fetch_release_prefers_verified_setup_installer(self):
        digest = "b" * 64
        release_payload = {
            "tag_name": "v4.5.6",
            "body": "Installer-based update",
            "html_url": "https://github.com/owner/project/releases/tag/v4.5.6",
            "assets": [
                {"name": "MiniRSS_4.5.6_win64.zip", "size": 123456,
                 "browser_download_url": "https://github.com/owner/project/releases/download/v4.5.6/MiniRSS_4.5.6_win64.zip"},
                {"name": "MiniRSS_4.5.6_win64.zip.sha256", "size": 90,
                 "browser_download_url": "https://github.com/owner/project/releases/download/v4.5.6/MiniRSS_4.5.6_win64.zip.sha256"},
                {"name": "MiniRSS_Setup_4.5.6_x64.exe", "size": 456789,
                 "browser_download_url": "https://github.com/owner/project/releases/download/v4.5.6/MiniRSS_Setup_4.5.6_x64.exe"},
                {"name": "MiniRSS_Setup_4.5.6_x64.exe.sha256", "size": 90,
                 "browser_download_url": "https://github.com/owner/project/releases/download/v4.5.6/MiniRSS_Setup_4.5.6_x64.exe.sha256"},
            ],
        }
        with patch.object(mini_rss, "urlopen", side_effect=[
            FakeResponse(json.dumps(release_payload).encode()),
            FakeResponse(f"{digest}  MiniRSS_Setup_4.5.6_x64.exe\\n".encode()),
        ]):
            release = mini_rss.fetch_github_release("owner/project")
        self.assertEqual(release["asset_type"], "installer")
        self.assertEqual(release["sha256"], digest)
        self.assertTrue(release["download_url"].endswith("MiniRSS_Setup_4.5.6_x64.exe"))

    def test_download_update_installer_and_verify_checksum(self):
        import hashlib
        payload = b"MZ" + b"x" * 120_000
        update = {
            "asset_type": "installer",
            "download_url": "https://github.com/owner/project/releases/download/v1/MiniRSS_Setup.exe",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        with patch.object(mini_rss, "urlopen", return_value=FakeResponse(payload)):
            folder, installer_path = mini_rss.download_update_package(update)
        self.assertTrue(Path(installer_path).name.endswith(".exe"))
        self.assertEqual(Path(installer_path).read_bytes(), payload)
        self.assertTrue(Path(folder).is_dir())

    def test_fetch_release_and_checksum(self):
        digest = "a" * 64
        release_payload = {
            "tag_name": "v9.8.7",
            "body": "Improvements",
            "html_url": "https://github.com/owner/project/releases/tag/v9.8.7",
            "assets": [
                {"name": "MiniRSS_9.8.7_win64.zip", "size": 123456,
                 "browser_download_url": "https://github.com/owner/project/releases/download/v9.8.7/MiniRSS_9.8.7_win64.zip"},
                {"name": "MiniRSS_9.8.7_win64.zip.sha256", "size": 90,
                 "browser_download_url": "https://github.com/owner/project/releases/download/v9.8.7/MiniRSS_9.8.7_win64.zip.sha256"},
            ],
        }
        with patch.object(mini_rss, "urlopen", side_effect=[
            FakeResponse(json.dumps(release_payload).encode()),
            FakeResponse(f"{digest}  MiniRSS_9.8.7_win64.zip\\n".encode()),
        ]):
            release = mini_rss.fetch_github_release("owner/project")
        self.assertEqual(release["version"], "9.8.7")
        self.assertEqual(release["sha256"], digest)
        self.assertIn("Improvements", release["notes"])


class PackageTests(unittest.TestCase):
    def test_update_package_contains_exe_and_sidecar(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dist = root / "dist"
            release = root / "release"
            dist.mkdir()
            exe = dist / "MiniRSS.exe"
            exe.write_bytes(b"MZ" + b"x" * 120_000)
            source = root / "mini_rss.py"
            source.write_text('APP_VERSION = "3.2.1"\\n', encoding="utf-8")
            with patch.object(create_update_package, "APP_SOURCE", source), \
                 patch.object(create_update_package, "EXE_SOURCE", exe), \
                 patch.object(create_update_package, "RELEASE_DIR", release):
                self.assertEqual(create_update_package.main(), 0)
            archive = release / "MiniRSS_3.2.1_win64.zip"
            sidecar = release / "MiniRSS_3.2.1_win64.zip.sha256"
            self.assertTrue(archive.exists())
            self.assertTrue(sidecar.exists())
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), sidecar.read_text().split()[0])
            with zipfile.ZipFile(archive) as zf:
                self.assertEqual(zf.namelist(), ["MiniRSS.exe"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
