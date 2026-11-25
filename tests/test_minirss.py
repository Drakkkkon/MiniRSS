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

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.payload


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


class GithubUpdateTests(unittest.TestCase):
    def test_normalize_repo(self):
        self.assertEqual(mini_rss.normalize_github_repo("https://github.com/owner/project/"), "owner/project")
        with self.assertRaises(ValueError):
            mini_rss.normalize_github_repo("owner/project/extra")

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
