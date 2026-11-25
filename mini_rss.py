from __future__ import annotations

import html
import hashlib
import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import webbrowser
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFilter, ImageTk
except Exception:  # Pillow / tray are optional when running directly from source.
    pystray = None
    Image = ImageDraw = ImageFilter = ImageTk = None

try:
    from winotify import Notification
except Exception:
    Notification = None

try:
    import winreg
except ImportError:  # pragma: no cover - available on Windows only
    winreg = None

APP_NAME = "MiniRSS"
APP_VERSION = "1.4.5"
REFRESH_INTERVAL_MS = 15 * 60 * 1000
UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000
REQUEST_TIMEOUT = 15
UPDATE_TIMEOUT = 45
MAX_UPDATE_BYTES = 120 * 1024 * 1024
MAX_ITEMS_PER_FEED = 60
MAX_FEED_BYTES = 4 * 1024 * 1024
ALL_FEEDS = "Все ленты"
FAVORITES_FILTER = "★ Избранное"


def data_dir() -> Path:
    """Return a per-user settings folder on Windows, with a portable fallback."""
    root = os.environ.get("APPDATA")
    path = Path(root) / APP_NAME if root else Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(relative: str) -> Path:
    """Resolve bundled assets in source mode and PyInstaller one-file mode."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


APP_DATA_DIR = data_dir()
DATA_FILE = APP_DATA_DIR / "feeds.json"
FAVORITES_FILE = APP_DATA_DIR / "favorites.json"
SETTINGS_FILE = APP_DATA_DIR / "settings.json"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

THEMES = {
    "Светлая": {
        "bg": "#f3f5fa", "surface": "#ffffff", "fg": "#202633", "muted": "#6f7b8d",
        "accent": "#526fe5", "accent_active": "#405fd2", "button": "#edf1f8",
        "heading": "#f2f4f8", "tree": "#ffffff", "selected": "#e4eaff",
        "border": "#e1e6ef", "text_bg": "#f8f9fc", "text_fg": "#303b4d",
        "input": "#ffffff", "disabled": "#aab4c4", "hover": "#e9eefb",
        "sidebar": "#edf1f8", "detail": "#f7f8fc", "accent_soft": "#e8edff",
    },
    "Тёмная": {
        "bg": "#191d25", "surface": "#242a35", "fg": "#ecf0f7", "muted": "#a5afbf",
        "accent": "#7894ff", "accent_active": "#91a7ff", "button": "#303846",
        "heading": "#2b3340", "tree": "#242a35", "selected": "#3b4b74",
        "border": "#363f4d", "text_bg": "#202630", "text_fg": "#e0e7f2",
        "input": "#202630", "disabled": "#657287", "hover": "#343e50",
        "sidebar": "#202630", "detail": "#202630", "accent_soft": "#2d3b60",
    },
    "iOS 27 · Liquid Glass": {
        "bg": "#f2f2f7", "surface": "#ffffff", "fg": "#17181d", "muted": "#858893",
        "accent": "#1687f8", "accent_active": "#0876e6", "button": "#ffffff",
        "heading": "#f8f8fb", "tree": "#ffffff", "selected": "#e4f1ff",
        "border": "#e5e6ed", "text_bg": "#ffffff", "text_fg": "#252832",
        "input": "#ffffff", "disabled": "#aeb2bd", "hover": "#edf4fd",
        "sidebar": "#f0f1f6", "detail": "#ffffff", "accent_soft": "#e5f2ff",
        "glass": "#ffffff", "glass_edge": "#e1e5ed", "glass_highlight": "#ffffff",
        "glass_shadow": "#d9dce5", "icon": "#505662",
    },
}

# Dark appearance counterpart from the same iOS Liquid Glass visual language.
GLASS_DARK_THEME = {
    "bg": "#101820", "surface": "#24313b", "fg": "#f5f7fa", "muted": "#a9b7c3",
    "accent": "#61b5ff", "accent_active": "#3599f4", "button": "#34434f",
    "heading": "#2b3944", "tree": "#202d37", "selected": "#36566e",
    "border": "#4a5a66", "text_bg": "#263540", "text_fg": "#edf3f8",
    "input": "#354653", "disabled": "#788894", "hover": "#3b5262",
    "sidebar": "#1e2b35", "detail": "#293943", "accent_soft": "#344f63",
    "glass": "#394c59", "glass_edge": "#718493", "glass_highlight": "#b9cbd8",
    "glass_shadow": "#15222b", "icon": "#e2edf5",
}

# Segoe MDL2 Assets is part of Windows 10/11 and provides crisp vector-like UI glyphs.
GLYPHS = {
    "rss": "\uE8F2", "home": "\uE80F", "favorite": "\uE734",
    "favorite_filled": "\uE735", "refresh": "\uE72C", "settings": "\uE713",
    "add": "\uE710", "sources": "\uE8F1", "delete": "\uE74D",
    "search": "\uE721", "open": "\uE8A7", "compact": "\uE8A2",
    "expand": "\uE8A7", "close": "\uE8BB", "github": "\uE7AD",
}
GLYPH_FALLBACKS = {
    "rss": "◉", "home": "⌂", "favorite": "☆", "favorite_filled": "★",
    "refresh": "↻", "settings": "⚙", "add": "+", "sources": "▤",
    "delete": "⌫", "search": "⌕", "open": "↗", "compact": "▣",
    "expand": "□", "close": "×", "github": "●",
}


# Sources have been chosen from published RSS endpoints. Users choose which to add.
PRESET_FEEDS = [
    {"group": "Казахстан", "title": "Новости Казахстана", "url": "https://news.google.com/rss/search?q=%D0%9A%D0%B0%D0%B7%D0%B0%D1%85%D1%81%D1%82%D0%B0%D0%BD&hl=ru&gl=KZ&ceid=KZ:ru"},
    {"group": "Казахстан", "title": "Новости Алматы", "url": "https://news.google.com/rss/search?q=%D0%90%D0%BB%D0%BC%D0%B0%D1%82%D1%8B&hl=ru&gl=KZ&ceid=KZ:ru"},
    {"group": "Русскоязычные новости", "title": "BBC News — Русская служба", "url": "https://feeds.bbci.co.uk/russian/rss.xml"},
    {"group": "Русскоязычные новости", "title": "DW — Русский", "url": "https://rss.dw.com/rdf/rss-ru-top"},
    {"group": "Русскоязычные новости", "title": "Meduza — все материалы", "url": "https://meduza.io/rss/all"},
    {"group": "Мировые новости", "title": "BBC News — Мир (англ.)", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"group": "Мировые новости", "title": "DW — English", "url": "https://rss.dw.com/rdf/rss-en-all"},
    {"group": "Технологии", "title": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"group": "Технологии", "title": "Hacker News", "url": "https://news.ycombinator.com/rss"},
    {"group": "Наука и космос", "title": "NASA — последние публикации", "url": "https://www.nasa.gov/feed/"},
    {"group": "Технологии", "title": "Rozetked · Google Новости", "url": "https://news.google.com/rss/search?q=site%3Arozetked.me&hl=ru&gl=RU&ceid=RU:ru"},
    {"group": "Технологии", "title": "iGuides · Google Новости", "url": "https://news.google.com/rss/search?q=site%3Aiguides.ru&hl=ru&gl=RU&ceid=RU:ru"},
    {"group": "Технологии", "title": "4PDA", "url": "https://4pda.to/feed/"},
]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def child_text(element: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if local_name(child.tag) in wanted:
            return "".join(child.itertext()).strip()
    return ""


def clean_html(value: str, limit: int = 900) -> str:
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value or "")
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def parse_date(value: str) -> float:
    if not value:
        return 0.0
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        normalized = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


def parse_feed(xml_bytes: bytes, fallback_title: str = "RSS") -> tuple[str, list[dict]]:
    """Parse RSS 2.0, RSS 1.0/RDF and Atom using only the Python standard library."""
    root = ET.fromstring(xml_bytes)
    root_kind = local_name(root.tag)
    channel = next((node for node in list(root) if local_name(node.tag) == "channel"), None)
    title = fallback_title
    entries: list[ET.Element] = []

    if root_kind == "feed":
        title = child_text(root, "title") or fallback_title
        entries = [node for node in list(root) if local_name(node.tag) == "entry"]
    elif root_kind == "rss":
        if channel is not None:
            title = child_text(channel, "title") or fallback_title
            entries = [node for node in list(channel) if local_name(node.tag) == "item"]
    else:  # RSS 1.0 / RDF and compatible feeds
        if channel is not None:
            title = child_text(channel, "title") or fallback_title
        entries = [node for node in list(root) if local_name(node.tag) == "item"]

    results: list[dict] = []
    for entry in entries[:MAX_ITEMS_PER_FEED]:
        item_title = child_text(entry, "title") or "Без названия"
        link = child_text(entry, "link")
        if not link:
            for node in list(entry):
                if local_name(node.tag) == "link":
                    rel = node.attrib.get("rel", "alternate")
                    if rel in ("alternate", ""):
                        link = node.attrib.get("href", "")
                        if link:
                            break
        summary = child_text(entry, "description", "summary", "encoded", "content")
        date_text = child_text(entry, "pubdate", "published", "updated", "date")
        results.append({
            "title": clean_html(item_title, 240),
            "link": link.strip(),
            "summary": clean_html(summary),
            "date": date_text.strip(),
            "timestamp": parse_date(date_text),
        })
    return clean_html(title, 100) or fallback_title, results


def fetch_feed(url: str, fallback_title: str = "RSS") -> tuple[str, list[dict]]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Укажите полный адрес, начинающийся с http:// или https://")
    request = Request(url, headers={
        "User-Agent": f"MiniRSS/{APP_VERSION} (Windows desktop RSS reader)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        payload = response.read(MAX_FEED_BYTES + 1)
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError("Лента слишком большая (более 4 МБ)")
    return parse_feed(payload, fallback_title)


def article_key(article: dict) -> str:
    link = (article.get("link") or "").strip()
    if link:
        return link
    return f"{article.get('feed_id', '')}|{article.get('title', '')}"


def version_tuple(value: str) -> tuple[int, ...]:
    """Parse a simple dotted numeric version such as 1.2.0 or v1.3."""
    parts = re.findall(r"\d+", str(value))
    if not parts:
        raise ValueError(f"Некорректный номер версии: {value!r}")
    return tuple(int(part) for part in parts)


def fetch_update_manifest(manifest_url: str) -> dict:
    parsed = urlparse(manifest_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Адрес манифеста обновлений должен начинаться с https://")
    request = Request(manifest_url, headers={"User-Agent": f"MiniRSS/{APP_VERSION}", "Accept": "application/json"})
    with urlopen(request, timeout=UPDATE_TIMEOUT) as response:
        payload = response.read(256 * 1024 + 1)
    if len(payload) > 256 * 1024:
        raise ValueError("Файл манифеста слишком большой")
    manifest = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(manifest, dict):
        raise ValueError("Неверный формат манифеста обновлений")
    version = str(manifest.get("version", "")).strip()
    download_url = str(manifest.get("download_url", "")).strip()
    checksum = str(manifest.get("sha256", "")).strip().lower()
    version_tuple(version)
    download_parsed = urlparse(download_url)
    if download_parsed.scheme != "https" or not download_parsed.netloc:
        raise ValueError("В манифесте указан некорректный HTTPS-адрес пакета")
    if not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("В манифесте отсутствует корректная SHA-256 контрольная сумма")
    return {
        "version": version,
        "download_url": download_url,
        "sha256": checksum,
        "notes": str(manifest.get("notes", ""))[:2000],
    }


def normalize_github_repo(value: str) -> str:
    """Validate and normalize a public GitHub repository as owner/name."""
    value = (value or "").strip()
    value = re.sub(r"^https?://github\.com/", "", value, flags=re.I).strip(" /")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", value):
        raise ValueError("Укажите публичный GitHub-репозиторий в формате владелец/название, например username/minirss.")
    return value


def _read_https_text(url: str, limit: int = 64 * 1024, accept: str = "text/plain") -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("GitHub вернул небезопасную ссылку. Ожидается HTTPS.")
    request = Request(url, headers={"User-Agent": f"MiniRSS/{APP_VERSION}", "Accept": accept})
    with urlopen(request, timeout=UPDATE_TIMEOUT) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise ValueError("Ответ GitHub слишком большой.")
    return payload.decode("utf-8-sig", errors="replace")


def fetch_github_release(repository: str) -> dict:
    """Read the latest public GitHub Release and its SHA-256 sidecar asset."""
    repository = normalize_github_repo(repository)
    api_url = f"https://api.github.com/repos/{repository}/releases/latest"
    request = Request(api_url, headers={
        "User-Agent": f"MiniRSS/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urlopen(request, timeout=UPDATE_TIMEOUT) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
    except HTTPError as exc:
        if exc.code == 404:
            raise ValueError("В репозитории пока нет опубликованного GitHub Release. Сначала выпустите релиз с тегом v1.3.0 или новее.") from exc
        if exc.code == 403:
            raise ValueError("GitHub ограничил запросы API. Попробуйте позже.") from exc
        raise ValueError(f"GitHub API вернул HTTP {exc.code}.") from exc
    if len(payload) > 2 * 1024 * 1024:
        raise ValueError("Ответ GitHub API слишком большой.")
    release = json.loads(payload.decode("utf-8-sig"))
    tag = str(release.get("tag_name", "")).strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    version_tuple(version)
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("GitHub Release вернул некорректный список файлов.")
    # Prefer the signed installer: Inno Setup handles locked files and reinstalls
    # over the existing application directory. Older releases remain supported
    # through the verified ZIP/EXE path below.
    installer_name = f"MiniRSS_Setup_{version}_x64.exe"
    installer_asset = next((a for a in assets if a.get("name") == installer_name), None)
    installer_checksum = next((a for a in assets if a.get("name") == installer_name + ".sha256"), None)
    if installer_asset and installer_checksum:
        selected_asset = installer_asset
        checksum_asset = installer_checksum
        asset_type = "installer"
    else:
        archive_name = f"MiniRSS_{version}_win64.zip"
        selected_asset = next((a for a in assets if a.get("name") == archive_name), None)
        checksum_asset = next((a for a in assets if a.get("name") == archive_name + ".sha256"), None)
        asset_type = "zip"
        if not selected_asset:
            raise ValueError(f"В релизе {tag} не найден установщик или архив обновления MiniRSS.")
        if not checksum_asset:
            raise ValueError(f"В релизе {tag} отсутствует SHA-256 для пакета обновления.")
    download_url = str(selected_asset.get("browser_download_url", "")).strip()
    checksum_url = str(checksum_asset.get("browser_download_url", "")).strip()
    if int(selected_asset.get("size", 0) or 0) > MAX_UPDATE_BYTES:
        raise ValueError("Пакет обновления больше допустимого лимита 120 МБ.")
    checksum_text = _read_https_text(checksum_url, limit=4096)
    match = re.search(r"(?i)\b([a-f0-9]{64})\b", checksum_text)
    if not match:
        raise ValueError("Не удалось прочитать SHA-256 из файла релиза.")
    return {
        "version": version,
        "download_url": download_url,
        "sha256": match.group(1).lower(),
        "asset_type": asset_type,
        "asset_name": str(selected_asset.get("name", "")),
        "notes": str(release.get("body", ""))[:2000],
        "html_url": str(release.get("html_url", "")),
        "tag_name": tag,
    }


def download_update_package(update: dict) -> tuple[str, str]:
    """Download and verify an installer or legacy ZIP, returning its temporary path."""
    parsed_download = urlparse(str(update.get("download_url", "")))
    if parsed_download.scheme != "https" or not parsed_download.netloc:
        raise ValueError("Пакет обновления можно скачивать только по HTTPS.")
    asset_type = update.get("asset_type", "zip")
    if asset_type not in ("installer", "zip"):
        raise ValueError("Релиз содержит неизвестный формат обновления.")
    folder = tempfile.mkdtemp(prefix="MiniRSS_update_")
    package_path = Path(folder) / ("MiniRSS_Setup.exe" if asset_type == "installer" else "update.zip")
    request = Request(update["download_url"], headers={"User-Agent": f"MiniRSS/{APP_VERSION}"})
    digest = hashlib.sha256()
    total = 0
    with urlopen(request, timeout=UPDATE_TIMEOUT) as response, package_path.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_UPDATE_BYTES:
                raise ValueError("Пакет обновления превышает лимит 120 МБ.")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest().lower() != str(update.get("sha256", "")).lower():
        raise ValueError("Контрольная сумма пакета не совпадает. Обновление отменено.")

    if asset_type == "installer":
        if package_path.stat().st_size < 100_000:
            raise ValueError("Размер установщика MiniRSS выглядит некорректным.")
        with package_path.open("rb") as source:
            if source.read(2) != b"MZ":
                raise ValueError("Скачанный установщик не является Windows EXE-файлом.")
        return folder, str(package_path)

    new_exe = Path(folder) / "MiniRSS.exe"
    with zipfile.ZipFile(package_path, "r") as archive:
        candidates = [info for info in archive.infolist() if Path(info.filename).name.lower() == "minirss.exe"]
        if not candidates:
            raise ValueError("В архиве обновления не найден MiniRSS.exe.")
        exe_info = candidates[0]
        if exe_info.file_size < 100_000 or exe_info.file_size > MAX_UPDATE_BYTES:
            raise ValueError("Размер MiniRSS.exe в пакете выглядит некорректным.")
        with archive.open(exe_info, "r") as source, new_exe.open("wb") as target:
            shutil.copyfileobj(source, target)
    return folder, str(new_exe)


def build_update_helper_script() -> str:
    """PowerShell helper that safely installs the verified package after MiniRSS exits."""
    return r'''param(
    [int]$ProcessId,
    [string]$Package,
    [string]$Target,
    [string]$TempDir,
    [bool]$UseInstaller
)
$ErrorActionPreference = 'Stop'
$logFolder = Join-Path $env:APPDATA 'MiniRSS'
$log = Join-Path $logFolder 'update.log'
try {
    New-Item -ItemType Directory -Force -Path $logFolder | Out-Null
} catch {}
function Write-UpdateLog([string]$Message) {
    try {
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -LiteralPath $log -Value "[$stamp] $Message" -Encoding UTF8
    } catch {}
}
try {
    Write-UpdateLog "Updater started. Target=$Target Package=$Package Installer=$UseInstaller"
    if (-not (Test-Path -LiteralPath $Package)) { throw "Файл обновления не найден: $Package" }
    if (-not (Test-Path -LiteralPath $Target)) { throw "Не найдена установленная программа: $Target" }

    # Wait for both the app PID and the PyInstaller one-file parent process.
    $processName = [IO.Path]::GetFileNameWithoutExtension($Target)
    $targetFullPath = [IO.Path]::GetFullPath($Target)
    $deadline = (Get-Date).AddMinutes(3)
    while ($true) {
        $targetProcesses = @(
            Get-Process -Name $processName -ErrorAction SilentlyContinue |
            Where-Object {
                $sameTarget = $false
                try {
                    $sameTarget = [string]::Equals(
                        [IO.Path]::GetFullPath($_.Path), $targetFullPath,
                        [StringComparison]::OrdinalIgnoreCase
                    )
                } catch {
                    $sameTarget = ($_.Id -eq $ProcessId)
                }
                $sameTarget
            }
        )
        if ($targetProcesses.Count -eq 0) { break }
        if ((Get-Date) -gt $deadline) {
            $ids = ($targetProcesses | ForEach-Object { $_.Id }) -join ','
            throw "MiniRSS всё ещё запущен (PID: $ids). Закройте все окна программы и повторите обновление."
        }
        Start-Sleep -Milliseconds 500
    }
    Start-Sleep -Seconds 2
    Write-UpdateLog 'All MiniRSS processes have exited.'

    if ($UseInstaller) {
        $targetDir = Split-Path -Parent $targetFullPath
        $probe = Join-Path $targetDir ('.minirss_write_test_' + [Guid]::NewGuid().ToString('N'))
        $requiresAdmin = $false
        try {
            [IO.File]::WriteAllText($probe, 'test')
            Remove-Item -LiteralPath $probe -Force
        } catch {
            $requiresAdmin = $true
            Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        }

        $installMode = if ($requiresAdmin) { '/ALLUSERS' } else { '/CURRENTUSER' }
        $quotedDir = $targetDir.Replace('"', '')
        $argumentLine = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /CLOSEAPPLICATIONS ' +
                        $installMode + ' /DIR="' + $quotedDir + '"'
        Write-UpdateLog "Launching Inno Setup. ElevationRequired=$requiresAdmin InstallMode=$installMode Dir=$targetDir"

        $startArgs = @{
            FilePath = $Package
            ArgumentList = $argumentLine
            PassThru = $true
            Wait = $true
            WorkingDirectory = $TempDir
        }
        if ($requiresAdmin) { $startArgs.Verb = 'RunAs' }
        $installer = Start-Process @startArgs
        Write-UpdateLog "Installer exit code: $($installer.ExitCode)"
        if ($installer.ExitCode -ne 0) {
            throw "Установщик завершился с кодом $($installer.ExitCode). Подробности: $log"
        }
        if (-not (Test-Path -LiteralPath $targetFullPath)) {
            throw 'После установки не найден MiniRSS.exe в исходной папке приложения.'
        }
        $installedSize = (Get-Item -LiteralPath $targetFullPath).Length
        if ($installedSize -lt 100000) { throw 'После установки размер MiniRSS.exe выглядит некорректным.' }
        Write-UpdateLog "Installer finished. New executable size=$installedSize"

        $newProcess = Start-Process -FilePath $targetFullPath -WorkingDirectory $targetDir -PassThru
        Start-Sleep -Seconds 6
        $newProcess.Refresh()
        if ($newProcess.HasExited) {
            throw "Новая версия MiniRSS завершилась сразу после запуска (код $($newProcess.ExitCode))."
        }
        Write-UpdateLog "Updated MiniRSS launched. PID=$($newProcess.Id)"
    } else {
        # Compatibility path for older releases that only publish a ZIP with MiniRSS.exe.
        $backup = "$targetFullPath.bak"
        $staged = "$targetFullPath.update"
        $replaced = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            try {
                Copy-Item -LiteralPath $Package -Destination $staged -Force
                if ((Get-Item -LiteralPath $staged).Length -lt 100000) {
                    throw 'Размер нового MiniRSS.exe выглядит некорректным.'
                }
                if (Test-Path -LiteralPath $targetFullPath) {
                    Copy-Item -LiteralPath $targetFullPath -Destination $backup -Force
                }
                Move-Item -LiteralPath $staged -Destination $targetFullPath -Force
                $replaced = $true
                break
            } catch {
                Remove-Item -LiteralPath $staged -Force -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 1
            }
        }
        if (-not $replaced) { throw 'Не удалось заменить MiniRSS.exe: файл всё ещё занят или папка защищена.' }
        Write-UpdateLog 'Legacy ZIP executable replaced.'
        Start-Process -FilePath $targetFullPath -WorkingDirectory (Split-Path -Parent $targetFullPath) | Out-Null
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }

    Write-UpdateLog 'Update completed successfully.'
    Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    $details = $_ | Out-String
    Write-UpdateLog "UPDATE FAILED: $details"
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        ('Не удалось обновить MiniRSS.' + [Environment]::NewLine + [Environment]::NewLine +
         $_.Exception.Message + [Environment]::NewLine + [Environment]::NewLine + 'Журнал: ' + $log),
        'Обновление MiniRSS'
    ) | Out-Null
}'''


def autostart_command() -> str:
    """Command used by the current-user Windows Run registry key."""
    if getattr(sys, "frozen", False):
        executable = str(Path(sys.executable).resolve())
        return f'"{executable}" --minimized'
    script = str(Path(__file__).resolve())
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = str(pythonw if pythonw.exists() else Path(sys.executable))
    return f'"{interpreter}" "{script}" --minimized'


class AddFeedDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Добавить RSS-ленту")
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Название (необязательно)").pack(anchor="w")
        self.name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.name_var, width=48).pack(fill="x", pady=(5, 12))
        ttk.Label(frame, text="Адрес RSS / Atom").pack(anchor="w")
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(frame, textvariable=self.url_var, width=48)
        url_entry.pack(fill="x", pady=(5, 14))
        url_entry.focus_set()
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Добавить", command=self.submit, style="Accent.TButton").pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda _event: self.submit())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        self.geometry(f"{self.winfo_reqwidth()}x{self.winfo_reqheight()}+{parent.winfo_rootx()+40}+{parent.winfo_rooty()+80}")
        self.grab_set()

    def submit(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Нет адреса", "Введите адрес RSS-ленты.", parent=self)
            return
        if not urlparse(url).scheme:
            url = "https://" + url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            messagebox.showwarning("Неверный адрес", "Адрес должен начинаться с http:// или https://", parent=self)
            return
        self.result = {"id": str(uuid.uuid4()), "title": self.name_var.get().strip() or parsed.netloc, "url": url}
        self.destroy()


class PresetFeedsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, presets: list[dict]):
        super().__init__(parent)
        self.title("Готовые RSS-источники")
        self.geometry("510x600")
        self.minsize(430, 440)
        self.transient(parent)
        self.result: list[dict] | None = None
        self.vars: dict[str, tk.BooleanVar] = {}

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Выберите источники, которые хотите подключить.", style="Sub.TLabel").pack(anchor="w", pady=(0, 9))

        canvas_frame = ttk.Frame(outer)
        canvas_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(canvas_frame, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=(2, 2, 8, 2))
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(canvas_window, width=e.width))
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        grouped: dict[str, list[dict]] = {}
        for feed in presets:
            grouped.setdefault(feed["group"], []).append(feed)
        for group_name, feeds in grouped.items():
            section = ttk.LabelFrame(content, text=group_name, padding=(9, 7))
            section.pack(fill="x", pady=(0, 8))
            for feed in feeds:
                var = tk.BooleanVar(value=False)
                self.vars[feed["url"]] = var
                row = ttk.Frame(section)
                row.pack(fill="x", anchor="w", pady=2)
                ttk.Checkbutton(row, text=feed["title"], variable=var).pack(side="left", anchor="w")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(11, 0))
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Добавить выбранные", command=self.submit, style="Accent.TButton").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _e: self.destroy())

    def submit(self):
        selected = [dict(feed, id=str(uuid.uuid4())) for feed in PRESET_FEEDS if self.vars[feed["url"]].get()]
        if not selected:
            messagebox.showinfo("Источники не выбраны", "Отметьте хотя бы один источник.", parent=self)
            return
        self.result = selected
        self.destroy()


class ToolTip:
    """Small native-looking tooltip for icon-only controls."""
    def __init__(self, widget, text: str, palette_getter):
        self.widget = widget
        self.text = text
        self.palette_getter = palette_getter
        self.window = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None):
        self.hide()
        try:
            self.after_id = self.widget.after(450, self.show)
        except tk.TclError:
            self.after_id = None

    def show(self):
        if self.window is not None or not self.text:
            return
        try:
            palette = self.palette_getter()
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 7
            self.window = tk.Toplevel(self.widget)
            self.window.wm_overrideredirect(True)
            self.window.wm_geometry(f"+{x}+{y}")
            label = tk.Label(
                self.window, text=self.text, bg=palette["tooltip_bg"], fg=palette["tooltip_fg"],
                font=("Segoe UI", 8), padx=9, pady=5, relief="flat", bd=0,
            )
            label.pack()
        except tk.TclError:
            self.window = None

    def hide(self, _event=None):
        if self.after_id is not None:
            try:
                self.widget.after_cancel(self.after_id)
            except tk.TclError:
                pass
            self.after_id = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


class MiniRSSApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"MiniRSS {APP_VERSION}")
        try:
            icon_file = resource_path("assets/minirss.ico")
            if icon_file.exists():
                self.root.iconbitmap(str(icon_file))
        except tk.TclError:
            pass
        self.root.geometry("980x760")
        self.root.minsize(760, 560)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.feeds: list[dict] = []
        self.articles: list[dict] = []
        self.filtered_articles: list[dict] = []
        self.favorites: dict[str, dict] = {}
        self.current_article: dict | None = None
        self.busy = False
        self.events: queue.Queue = queue.Queue()
        self.filter_var = tk.StringVar(value=ALL_FEEDS)
        self.filter_map: dict[str, str] = {}
        self.search_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Готово к работе")
        self.theme_var = tk.StringVar(value="Светлая")
        self.glass_appearance_var = tk.StringVar(value="Светлая")
        self.glass_effect_var = tk.StringVar(value="Однотонный")
        self.opacity_var = tk.DoubleVar(value=1.0)
        self.always_on_top_var = tk.BooleanVar(value=False)
        self.autostart_var = tk.BooleanVar(value=False)
        self.notifications_var = tk.BooleanVar(value=True)
        self.close_to_tray_var = tk.BooleanVar(value=True)
        self.auto_check_updates_var = tk.BooleanVar(value=True)
        self.update_manifest_url_var = tk.StringVar(value="")  # Legacy setting retained for backward compatibility.
        self.github_repo_var = tk.StringVar(value="Drakkkkon/MiniRSS")
        self.compact_mode = False
        self.tray_icon = None
        self.tray_available = False
        self.update_check_busy = False
        self.update_download_busy = False
        self.detail_title = None
        self.detail_source = None
        self.description = None
        self.icon_font = self._detect_icon_font()
        self._tooltips: list[ToolTip] = []
        self._icon_buttons: list[ttk.Button] = []
        self._icon_images: dict[tuple, object] = {}
        self._glass_surface_labels: dict[str, tk.Label] = {}
        self._glass_surface_photos: dict[str, object] = {}
        self._glass_surface_sizes: dict[str, tuple[int, int, str, str]] = {}

        self._load_settings()
        self._style()
        self._build_ui()
        self._style()  # Apply image-based symbols to widgets created by _build_ui.
        self._apply_theme_layout()
        self._load_feeds()
        self._load_favorites()
        self._render_feed_filter()
        self._apply_window_settings()
        self._refresh_selected(silent=True)
        self.root.after(150, self._poll_events)
        self.root.after(REFRESH_INTERVAL_MS, self._auto_refresh)
        self._start_tray()
        if self.compact_mode:
            self._set_compact_mode(True, save=False)
        if "--minimized" in sys.argv and self.tray_available:
            self.root.after(700, self.root.withdraw)
        if self.auto_check_updates_var.get() and self.github_repo_var.get().strip():
            self.root.after(12_000, lambda: self._check_for_updates(silent=True))
        self.root.after(UPDATE_CHECK_INTERVAL_MS, self._scheduled_update_check)

    def _attach_glass_surface(self, widget, key: str):
        if Image is None or ImageDraw is None or ImageFilter is None or ImageTk is None:
            return
        label = tk.Label(widget, bd=0, highlightthickness=0, bg=self._palette()["bg"])
        label.place(x=0, y=0, relwidth=1, relheight=1)
        label.lower()
        self._glass_surface_labels[key] = label
        widget.bind(
            "<Configure>",
            lambda _event, surface_key=key: self.root.after_idle(
                lambda: self._render_glass_surface(surface_key)
            ),
            add="+",
        )
        self.root.after_idle(lambda: self._render_glass_surface(key))

    def _render_glass_surface(self, key: str):
        label = self._glass_surface_labels.get(key)
        if label is None:
            return
        if not self._is_glass_theme():
            label.place_forget()
            return
        widget = label.master
        width, height = widget.winfo_width(), widget.winfo_height()
        if width < 20 or height < 20:
            return
        palette = self._palette()
        cache_key = (width, height, self.glass_appearance_var.get(), self.glass_effect_var.get())
        if self._glass_surface_sizes.get(key) != cache_key:
            dark = self.glass_appearance_var.get() == "Тёмная"
            transparent = self.glass_effect_var.get() == "Прозрачный"
            image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rounded_rectangle(
                (5, 7, width - 5, height - 3), radius=min(26, height // 3),
                fill=(0, 0, 0, 44 if dark else 24)
            )
            image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(7)))
            draw = ImageDraw.Draw(image)
            base = palette["glass"]
            rgb = tuple(int(base[i:i + 2], 16) for i in (1, 3, 5))
            alpha = 168 if transparent else (205 if dark else 238)
            draw.rounded_rectangle(
                (2, 2, width - 3, height - 5), radius=min(25, height // 3),
                fill=(*rgb, alpha),
                outline=(*tuple(int(palette["glass_edge"][i:i + 2], 16) for i in (1, 3, 5)),
                         205 if transparent else 225),
                width=1,
            )
            # Soft top sheen, rather than a flat border, echoes the iOS control surfaces.
            draw.arc((5, 2, width - 7, max(18, height // 2)), 190, 350,
                     fill=(255, 255, 255, 190 if not dark else 135), width=2)
            draw.line((18, 4, max(19, width - 18), 4),
                      fill=(255, 255, 255, 95 if transparent else 150), width=1)
            photo = ImageTk.PhotoImage(image)
            self._glass_surface_photos[key] = photo
            self._glass_surface_sizes[key] = cache_key
        label.configure(image=self._glass_surface_photos[key], bg=palette["bg"])
        label.place(x=0, y=0, relwidth=1, relheight=1)
        label.lower()

    def _refresh_glass_surfaces(self):
        for key in list(self._glass_surface_labels):
            self._render_glass_surface(key)

    def _change_glass_appearance(self, value: str):
        if value not in ("Светлая", "Тёмная"):
            return
        self.glass_appearance_var.set(value)
        self._glass_surface_sizes.clear()
        self._icon_images.clear()
        self._style()
        self._save_settings()

    def _change_glass_effect(self, value: str):
        if value not in ("Прозрачный", "Однотонный"):
            return
        self.glass_effect_var.set(value)
        self._glass_surface_sizes.clear()
        self._icon_images.clear()
        self._style()
        self._save_settings()

    def _detect_icon_font(self):
        try:
            families = set(tkfont.families(self.root))
        except tk.TclError:
            families = set()
        for family in ("Segoe MDL2 Assets", "Segoe Fluent Icons", "Segoe UI Symbol"):
            if family in families:
                return (family, 14)
        return ("Segoe UI Symbol", 14)

    def _set_native_titlebar_theme(self):
        """Apply Windows 11 Mica, rounded corners and matching title-bar colors when available."""
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            glass_mode = self._is_glass_theme()
            dark_mode = (
                self.theme_var.get() == "Тёмная"
                or (self._is_glass_theme() and self.glass_appearance_var.get() == "Тёмная")
            )

            # DWMWA_USE_IMMERSIVE_DARK_MODE: 20 on current Windows 11, 19 on older builds.
            dark_value = ctypes.c_int(1 if dark_mode else 0)
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(dark_value), ctypes.sizeof(dark_value)
                )
                if result == 0:
                    break

            # DWMSBT_MAINWINDOW (2) supplies native Mica behind the glass UI.
            # Older Windows builds simply ignore unsupported attributes.
            backdrop = ctypes.c_int(2 if glass_mode else 1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop)
            )
            corners = ctypes.c_int(2 if glass_mode else 1)  # DWMWCP_ROUND / DEFAULT
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(corners), ctypes.sizeof(corners)
            )

            def colorref(value):
                value = value.lstrip("#")
                red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
                return red | (green << 8) | (blue << 16)

            if glass_mode:
                palette = self._palette()
                native_colors = (
                    (34, palette["glass_edge"]), (35, palette["bg"]), (36, palette["fg"])
                )
                for attribute, color in native_colors:
                    native_color = ctypes.c_int(colorref(color))
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attribute, ctypes.byref(native_color), ctypes.sizeof(native_color)
                    )
            else:
                # Restore Windows defaults so changing themes never leaves a tinted title bar behind.
                for attribute in (34, 35, 36):
                    native_color = ctypes.c_uint(0xFFFFFFFF)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attribute, ctypes.byref(native_color), ctypes.sizeof(native_color)
                    )
        except Exception:
            pass

    def _is_glass_theme(self) -> bool:
        return self.theme_var.get() == "iOS 27 · Liquid Glass"

    def _palette(self):
        colors = dict(THEMES[self.theme_var.get()])
        if self._is_glass_theme():
            if self.glass_appearance_var.get() == "Тёмная":
                colors.update(GLASS_DARK_THEME)
            if self.glass_effect_var.get() == "Прозрачный":
                # More visible background and cooler translucent surfaces.
                if self.glass_appearance_var.get() == "Тёмная":
                    colors.update({
                        "bg": "#111f2b", "surface": "#2a3b48", "glass": "#465c6b",
                        "glass_edge": "#829aaa", "glass_highlight": "#d5e3ec",
                        "glass_shadow": "#14222d", "tree": "#21323e",
                        "detail": "#304451", "input": "#405563",
                        "heading": "#344957", "sidebar": "#1e303d",
                        "selected": "#3f637c", "accent_soft": "#3d6079",
                    })
                else:
                    colors.update({
                        "bg": "#eaf0f8", "surface": "#f2f6fb", "glass": "#f4f8fd",
                        "glass_edge": "#d3dfec", "glass_highlight": "#ffffff",
                        "glass_shadow": "#d4deeb", "tree": "#f3f7fc",
                        "detail": "#f0f5fa", "input": "#f7faff",
                        "heading": "#edf3fa", "sidebar": "#e7eef7",
                        "selected": "#e0efff", "accent_soft": "#e1efff",
                    })
            else:
                # One-tone glass keeps the content surface calm and ordered.
                if self.glass_appearance_var.get() == "Тёмная":
                    colors.update({
                        "bg": "#171b20", "surface": "#252b32", "glass": "#303740",
                        "glass_edge": "#59636f", "glass_highlight": "#87939f",
                        "glass_shadow": "#101419", "tree": "#21272e",
                        "detail": "#292f37", "input": "#303740",
                        "heading": "#303740", "sidebar": "#20262d",
                    })
        tooltip_bg = "#242a35" if self.theme_var.get() == "Тёмная" else (
            "#20252c" if self._is_glass_theme() and self.glass_appearance_var.get() == "Тёмная" else
            "#303744" if self._is_glass_theme() else "#202633"
        )
        return {**colors, "tooltip_bg": tooltip_bg, "tooltip_fg": "#ffffff"}

    def _glyph(self, name: str) -> str:
        if self.icon_font[0] == "Segoe MDL2 Assets":
            return GLYPHS[name]
        return GLYPH_FALLBACKS.get(name, "•")

    def _make_icon_photo(self, name: str, color: str, size: int = 22,
                         tile: bool = False, active: bool = False):
        """Draw crisp, SF-Symbol-inspired outline icons for the Liquid Glass theme."""
        if Image is None or ImageDraw is None or ImageTk is None:
            return None
        cache_key = (
            name, color, size, tile, active,
            self.glass_appearance_var.get(), self.glass_effect_var.get()
        )
        if cache_key in self._icon_images:
            return self._icon_images[cache_key]
        scale = 3
        canvas_size = 64
        image = Image.new("RGBA", (canvas_size * scale, canvas_size * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        def xy(value):
            return int(round(value * scale))

        def line(points, width=4):
            draw.line([(xy(x), xy(y)) for x, y in points], fill=color,
                      width=xy(width), joint="curve")

        def ellipse(bounds, width=4, fill=None):
            box = tuple(xy(v) for v in bounds)
            draw.ellipse(box, outline=color if fill is None else None,
                         fill=fill, width=xy(width))

        def rounded(bounds, radius=7, width=4, fill=None):
            box = tuple(xy(v) for v in bounds)
            draw.rounded_rectangle(box, radius=xy(radius),
                                   outline=color if fill is None else None,
                                   fill=fill, width=xy(width))
        if tile:
            palette = self._palette()
            dark = self.glass_appearance_var.get() == "Тёмная"
            transparent = self.glass_effect_var.get() == "Прозрачный"
            shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rounded_rectangle(
                (xy(5), xy(7), xy(59), xy(61)),
                radius=xy(19), fill=(0, 0, 0, 48 if dark else 25)
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(xy(3)))
            image.alpha_composite(shadow)
            draw = ImageDraw.Draw(image)
            body = palette["accent_soft"] if active else palette["glass"]
            body_rgb = tuple(int(body[i:i + 2], 16) for i in (1, 3, 5))
            alpha = 150 if transparent else (205 if dark else 238)
            if active:
                alpha = min(245, alpha + 18)
            draw.rounded_rectangle(
                (xy(3), xy(3), xy(61), xy(61)),
                radius=xy(19),
                fill=(*body_rgb, alpha),
                outline=(*tuple(int(palette["glass_edge"][i:i + 2], 16) for i in (1, 3, 5)),
                         185 if transparent else 220),
                width=xy(1),
            )
            # A thin upper reflection gives the tile a polished glass edge.
            draw.arc((xy(5), xy(4), xy(59), xy(45)), 190, 350,
                     fill=(255, 255, 255, 190 if not dark else 145), width=xy(2))
            draw.line((xy(16), xy(6), xy(48), xy(6)),
                      fill=(255, 255, 255, 95), width=xy(1))


        if name == "rss":
            ellipse((12, 44, 20, 52), fill=color)
            draw.arc(tuple(xy(v) for v in (10, 32, 34, 56)), 270, 360, fill=color, width=xy(5))
            draw.arc(tuple(xy(v) for v in (10, 16, 50, 56)), 270, 360, fill=color, width=xy(5))
        elif name == "home":
            line([(8, 29), (32, 9), (56, 29)], 5)
            line([(15, 26), (15, 55), (49, 55), (49, 26)], 5)
            line([(27, 55), (27, 39), (37, 39), (37, 55)], 4)
        elif name in ("favorite", "favorite_filled"):
            points = [(32, 7), (39, 24), (58, 25), (43, 38), (48, 57),
                      (32, 46), (16, 57), (21, 38), (6, 25), (25, 24)]
            if name == "favorite_filled":
                draw.polygon([(xy(x), xy(y)) for x, y in points], fill=color)
            else:
                line(points + [points[0]], 4)
        elif name == "refresh":
            draw.arc(tuple(xy(v) for v in (10, 10, 54, 54)), 45, 315, fill=color, width=xy(5))
            line([(48, 12), (54, 12), (54, 19)], 5)
            line([(16, 52), (10, 52), (10, 45)], 5)
        elif name == "settings":
            import math
            ellipse((18, 18, 46, 46), width=5)
            ellipse((27, 27, 37, 37), width=4)
            for angle in range(0, 360, 45):
                a = math.radians(angle)
                x1, y1 = 32 + 22 * math.cos(a), 32 + 22 * math.sin(a)
                x2, y2 = 32 + 28 * math.cos(a), 32 + 28 * math.sin(a)
                line([(x1, y1), (x2, y2)], 5)
        elif name == "add":
            line([(32, 12), (32, 52)], 5)
            line([(12, 32), (52, 32)], 5)
        elif name == "sources":
            rounded((14, 10, 50, 43), 6, 4)
            line([(22, 21), (42, 21)], 3)
            line([(22, 29), (39, 29)], 3)
            line([(22, 37), (35, 37)], 3)
            line([(19, 49), (45, 49)], 4)
            line([(24, 55), (40, 55)], 4)
        elif name == "delete":
            rounded((17, 20, 47, 55), 5, 4)
            line([(12, 15), (52, 15)], 4)
            line([(24, 10), (40, 10)], 4)
            line([(26, 27), (26, 48)], 3)
            line([(38, 27), (38, 48)], 3)
        elif name == "search":
            ellipse((9, 8, 43, 42), width=5)
            line([(36, 36), (55, 55)], 5)
        elif name == "open":
            rounded((9, 19, 43, 55), 5, 4)
            line([(28, 36), (54, 10), (54, 27)], 5)
            line([(54, 10), (37, 10)], 5)
        elif name == "compact":
            rounded((8, 13, 56, 51), 6, 4)
            line([(8, 24), (56, 24)], 4)
            line([(17, 18), (19, 18)], 4)
            line([(26, 18), (28, 18)], 4)
        elif name == "expand":
            line([(10, 26), (10, 10), (26, 10)], 5)
            line([(38, 10), (54, 10), (54, 26)], 5)
            line([(54, 38), (54, 54), (38, 54)], 5)
            line([(26, 54), (10, 54), (10, 38)], 5)
        elif name == "close":
            line([(15, 15), (49, 49)], 5)
            line([(49, 15), (15, 49)], 5)
        elif name == "github":
            ellipse((10, 10, 54, 54), width=5)
            line([(21, 39), (21, 28), (27, 22), (37, 22), (43, 28), (43, 39)], 4)
            line([(25, 22), (23, 15)], 4)
            line([(39, 22), (41, 15)], 4)
        else:
            ellipse((17, 17, 47, 47), width=4)

        resampling = getattr(Image, "Resampling", Image).LANCZOS
        image = image.resize((size, size), resampling)
        photo = ImageTk.PhotoImage(image)
        self._icon_images[cache_key] = photo
        return photo

    def _refresh_icon_button(self, button):
        name = getattr(button, "_minirss_icon_name", None)
        if not name:
            return
        glass_mode = self._is_glass_theme()
        if glass_mode:
            colors = self._palette()
            style_name = str(button.cget("style"))
            is_active = "Active" in style_name or name == "favorite_filled"
            color = ("#ffffff" if is_active and self.glass_appearance_var.get() == "Тёмная"
                     else colors["accent"] if is_active else colors.get("icon", colors["fg"]))
            photo = self._make_icon_photo(name, color, 40, tile=True, active=is_active)
            if photo is not None:
                button.configure(text="", image=photo, compound="center", width=0)
                button._minirss_image = photo
                return
        button.configure(
            image="", text=self._glyph(name), compound="center",
            width=getattr(button, "_minirss_width", 3)
        )
        button._minirss_image = None

    def _refresh_icon_buttons(self):
        for button in getattr(self, "_icon_buttons", []):
            try:
                self._refresh_icon_button(button)
            except tk.TclError:
                pass

    def _set_icon_button_symbol(self, button, name: str):
        if button is None:
            return
        button._minirss_icon_name = name
        self._refresh_icon_button(button)

    def _icon_button(self, parent, glyph: str, tooltip: str, command, style="Icon.TButton", width=3):
        name = next((key for key, value in GLYPHS.items() if value == glyph), None)
        display_glyph = self._glyph(name) if name else glyph
        button = ttk.Button(parent, text=display_glyph, command=command, style=style, width=width)
        button._minirss_width = width
        if name:
            button._minirss_icon_name = name
            self._icon_buttons.append(button)
            self._refresh_icon_button(button)
        self._tooltips.append(ToolTip(button, tooltip, self._palette))
        return button

    # ------------------------------- Settings -------------------------------
    def _load_settings(self):
        defaults = {
            "theme": "Светлая", "glass_appearance": "Светлая", "glass_effect": "Однотонный",
            "opacity": 100, "always_on_top": False, "compact": False,
            "autostart": False, "notifications": True, "close_to_tray": True,
            "auto_check_updates": True, "update_manifest_url": "", "github_repo": "Drakkkkon/MiniRSS",
        }
        try:
            if SETTINGS_FILE.exists():
                raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    defaults.update(raw)
        except (OSError, json.JSONDecodeError):
            pass
        self.theme_var.set(defaults.get("theme") if defaults.get("theme") in THEMES else "Светлая")
        appearance = str(defaults.get("glass_appearance", "Светлая"))
        self.glass_appearance_var.set(appearance if appearance in ("Светлая", "Тёмная") else "Светлая")
        effect = str(defaults.get("glass_effect", "Однотонный"))
        self.glass_effect_var.set(effect if effect in ("Прозрачный", "Однотонный") else "Однотонный")
        try:
            opacity = max(60, min(100, int(defaults.get("opacity", 100)))) / 100
        except (TypeError, ValueError):
            opacity = 1.0
        self.opacity_var.set(opacity)
        self.always_on_top_var.set(bool(defaults.get("always_on_top", False)))
        self.compact_mode = bool(defaults.get("compact", False))
        self.autostart_var.set(bool(defaults.get("autostart", False)))
        self.notifications_var.set(bool(defaults.get("notifications", True)))
        self.close_to_tray_var.set(bool(defaults.get("close_to_tray", True)))
        self.auto_check_updates_var.set(bool(defaults.get("auto_check_updates", True)))
        self.update_manifest_url_var.set(str(defaults.get("update_manifest_url", "")))
        self.github_repo_var.set(str(defaults.get("github_repo") or "Drakkkkon/MiniRSS"))

    def _save_settings(self):
        payload = {
            "theme": self.theme_var.get(),
            "glass_appearance": self.glass_appearance_var.get(),
            "glass_effect": self.glass_effect_var.get(),
            "opacity": round(float(self.opacity_var.get()) * 100),
            "always_on_top": bool(self.always_on_top_var.get()),
            "compact": bool(self.compact_mode),
            "autostart": bool(self.autostart_var.get()),
            "notifications": bool(self.notifications_var.get()),
            "close_to_tray": bool(self.close_to_tray_var.get()),
            "auto_check_updates": bool(self.auto_check_updates_var.get()),
            "update_manifest_url": self.update_manifest_url_var.get().strip(),
            "github_repo": self.github_repo_var.get().strip(),
        }
        try:
            SETTINGS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.status_var.set(f"Не удалось сохранить настройки: {exc}")

    def _apply_window_settings(self):
        self._apply_opacity(self.opacity_var.get())
        self._apply_topmost()

    def _apply_opacity(self, value):
        try:
            opacity = max(0.60, min(1.0, float(value)))
            self.opacity_var.set(opacity)
            self.root.attributes("-alpha", opacity)
        except (tk.TclError, ValueError, TypeError):
            self.status_var.set("Прозрачность не поддерживается этой системой")

    def _apply_topmost(self):
        try:
            self.root.attributes("-topmost", bool(self.always_on_top_var.get()))
        except tk.TclError:
            pass

    def _on_topmost_change(self):
        self._apply_topmost()
        self._save_settings()

    def _set_autostart(self):
        if winreg is None:
            self.autostart_var.set(False)
            messagebox.showwarning("Автозапуск", "Автозапуск доступен только в Windows.", parent=self.root)
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE) as key:
                if self.autostart_var.get():
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            self.autostart_var.set(not self.autostart_var.get())
            messagebox.showerror("Автозапуск", f"Не удалось изменить автозапуск Windows:\n{exc}", parent=self.root)
            return
        self._save_settings()

    def _style(self):
        colors = self._palette()
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        base_font = ("Segoe UI", 9)
        title_font = ("Segoe UI", 19, "bold")
        style.configure("TFrame", background=colors["bg"])
        style.configure("Sidebar.TFrame", background=colors["sidebar"])
        style.configure("Card.TFrame", background=colors["surface"])
        style.configure("Detail.TFrame", background=colors["detail"])
        style.configure("TLabel", background=colors["bg"], foreground=colors["fg"], font=base_font)
        style.configure("Panel.TLabel", background=colors["surface"], foreground=colors["fg"], font=base_font)
        style.configure("Detail.TLabel", background=colors["detail"], foreground=colors["fg"], font=base_font)
        style.configure("Header.TLabel", font=title_font, foreground=colors["fg"], background=colors["bg"])
        style.configure("Sub.TLabel", foreground=colors["muted"], background=colors["bg"], font=("Segoe UI", 8))
        style.configure("CardSub.TLabel", foreground=colors["muted"], background=colors["surface"], font=("Segoe UI", 8))
        style.configure("DetailSub.TLabel", foreground=colors["muted"], background=colors["detail"], font=("Segoe UI", 8))
        style.configure("TButton", font=base_font, padding=(10, 7), background=colors["button"], foreground=colors["fg"], borderwidth=0)
        style.map("TButton", background=[("active", colors["hover"]), ("pressed", colors["selected"])], foreground=[("disabled", colors["muted"])])
        style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"), background=colors["accent"], foreground="#ffffff", padding=(12, 8), borderwidth=0)
        style.map("Accent.TButton", background=[("active", colors["accent_active"]), ("disabled", colors["disabled"])], foreground=[("disabled", "#ffffff")])
        style.configure("Icon.TButton", font=self.icon_font, padding=(8, 7), width=3, background=colors["surface"], foreground=colors["fg"], borderwidth=0, relief="flat")
        style.map("Icon.TButton", background=[("active", colors["hover"]), ("pressed", colors["selected"])], foreground=[("active", colors["accent"]), ("disabled", colors["muted"])])
        style.configure("Nav.TButton", font=(self.icon_font[0], 17), padding=(8, 11), width=3, background=colors["sidebar"], foreground=colors["muted"], borderwidth=0, relief="flat")
        style.map("Nav.TButton", background=[("active", colors["hover"])], foreground=[("active", colors["accent"])])
        style.configure("NavActive.TButton", font=(self.icon_font[0], 17), padding=(8, 11), width=3, background=colors["accent_soft"], foreground=colors["accent"], borderwidth=0, relief="flat")
        style.map("NavActive.TButton", background=[("active", colors["accent_soft"])], foreground=[("active", colors["accent"])])
        style.configure("Treeview", font=("Segoe UI", 9), rowheight=34, background=colors["tree"],
                        fieldbackground=colors["tree"], foreground=colors["fg"], borderwidth=0, relief="flat")
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background=colors["heading"],
                        foreground=colors["fg"], relief="flat", padding=(8, 9))
        style.map("Treeview", background=[("selected", colors["selected"])], foreground=[("selected", colors["fg"])])
        style.configure("TCombobox", padding=(8, 7), fieldbackground=colors["input"], background=colors["input"], foreground=colors["fg"], borderwidth=0, arrowsize=12)
        style.map("TCombobox", fieldbackground=[("readonly", colors["input"])], foreground=[("readonly", colors["fg"])])
        style.configure("TEntry", padding=(9, 8), fieldbackground=colors["input"], foreground=colors["fg"], borderwidth=0)
        style.configure("TCheckbutton", background=colors["bg"], foreground=colors["fg"], font=base_font)
        style.map("TCheckbutton", background=[("active", colors["bg"])])
        style.configure("TLabelframe", background=colors["bg"], foreground=colors["fg"], bordercolor=colors["border"])
        style.configure("TLabelframe.Label", background=colors["bg"], foreground=colors["fg"], font=("Segoe UI", 9, "bold"))
        style.configure("GlassHeader.TFrame", background=colors["bg"], borderwidth=0, relief="flat")
        if self._is_glass_theme():
            # Rounded image-backed glass surfaces and iOS-like controls sit on top
            # of a restrained neutral backdrop; all other themes keep their styling.
            style.configure("GlassHeader.TFrame", background=colors["glass"], borderwidth=1,
                            bordercolor=colors["glass_highlight"], lightcolor=colors["glass_highlight"],
                            darkcolor=colors["glass_edge"], relief="solid")
            style.configure("TButton", font=("Segoe UI", 10), padding=(13, 10),
                            background=colors["glass"], foreground=colors["fg"],
                            borderwidth=1, bordercolor=colors["glass_edge"],
                            lightcolor=colors["glass_highlight"], darkcolor=colors["glass_shadow"],
                            relief="raised")
            style.map("TButton", background=[("active", colors["glass_highlight"]),
                                              ("pressed", colors["selected"])],
                      foreground=[("disabled", colors["disabled"])])
            style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(16, 10),
                            background=colors["accent"], foreground="#ffffff",
                            borderwidth=1, bordercolor=colors["glass_highlight"],
                            lightcolor=colors["glass_highlight"], darkcolor=colors["accent_active"],
                            relief="raised")
            style.map("Accent.TButton", background=[("active", colors["accent_active"]),
                                                       ("pressed", colors["accent"])])
            style.configure("Icon.TButton", font=self.icon_font, padding=(2, 2), width=3,
                            background=colors["bg"], foreground=colors["fg"],
                            borderwidth=0, relief="flat")
            style.map("Icon.TButton", background=[("active", colors["glass_highlight"]),
                                                    ("pressed", colors["selected"])])
            style.configure("Card.TFrame", background=colors["surface"], borderwidth=1,
                            bordercolor=colors["glass_highlight"], lightcolor=colors["glass_highlight"],
                            darkcolor=colors["glass_edge"], relief="solid")
            style.configure("Detail.TFrame", background=colors["detail"], borderwidth=1,
                            bordercolor=colors["glass_edge"], lightcolor=colors["glass_highlight"],
                            darkcolor=colors["glass_shadow"], relief="solid")
            style.configure("Sidebar.TFrame", background=colors["sidebar"])
            style.configure("Header.TLabel", font=("Segoe UI", 24, "bold"),
                            foreground=colors["fg"], background=colors["glass"])
            style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=colors["muted"],
                            background=colors["glass"])
            style.configure("Treeview", font=("Segoe UI", 10), rowheight=46,
                            background=colors["tree"], fieldbackground=colors["tree"],
                            foreground=colors["fg"], borderwidth=0, relief="flat")
            style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                            background=colors["heading"], foreground=colors["muted"],
                            relief="flat", padding=(13, 12), borderwidth=0)
            style.map("Treeview", background=[("selected", colors["selected"])],
                      foreground=[("selected", colors["fg"])])
            style.configure("TCombobox", padding=(12, 10), fieldbackground=colors["input"],
                            background=colors["glass"], foreground=colors["fg"],
                            borderwidth=1, bordercolor=colors["glass_edge"], arrowsize=14)
            style.configure("TEntry", padding=(12, 10), fieldbackground=colors["input"],
                            foreground=colors["fg"], borderwidth=1, bordercolor=colors["glass_edge"])
            style.configure("TSeparator", background=colors["glass_edge"])
            style.configure("Dock.TFrame", background=colors["bg"], borderwidth=0, relief="flat")
            style.configure("Dock.TButton", font=(self.icon_font[0], 17), padding=(2, 2),
                            background=colors["bg"], foreground=colors["icon"],
                            borderwidth=0, relief="flat")
            style.map("Dock.TButton", background=[("active", colors["hover"]),
                                                    ("pressed", colors["selected"])],
                      foreground=[("active", colors["accent"])])
            style.configure("DockActive.TButton", font=(self.icon_font[0], 17), padding=(2, 2),
                            background=colors["bg"], foreground=colors["accent"],
                            borderwidth=0, relief="flat")
            style.map("DockActive.TButton", background=[("active", colors["hover"])],
                      foreground=[("active", colors["accent"])])
            style.configure("GlassOptions.TLabelframe", background=colors["surface"],
                            bordercolor=colors["glass_edge"], borderwidth=1, relief="solid")
            style.configure("GlassOptions.TLabelframe.Label", background=colors["surface"],
                            foreground=colors["fg"], font=("Segoe UI", 9, "bold"))
            style.configure("Glass.TRadiobutton", background=colors["surface"],
                            foreground=colors["fg"], font=("Segoe UI", 9), padding=(5, 4))
            style.map("Glass.TRadiobutton", background=[("active", colors["surface"])],
                      foreground=[("selected", colors["accent"])])
        self.root.configure(bg=colors["bg"])
        if hasattr(self, "logo"):
            if self._is_glass_theme():
                self.logo.configure(bg=colors["accent_soft"], fg=colors["accent"],
                                    font=(self.icon_font[0], 20), padx=14, pady=9)
            else:
                self.logo.configure(bg=colors["accent"], fg="#ffffff",
                                    font=(self.icon_font[0], 19), padx=12, pady=8)
        self._set_native_titlebar_theme()
        if self.description is not None:
            glass_mode = self._is_glass_theme()
            self.description.configure(
                bg=colors["detail"], fg=colors["text_fg"], insertbackground=colors["text_fg"],
                highlightthickness=1 if glass_mode else 0,
                highlightbackground=colors.get("glass_edge", colors["border"]),
                highlightcolor=colors["accent"],
            )
        if hasattr(self, "nav_buttons"):
            self._update_nav_state()
        self._refresh_icon_buttons()
        if hasattr(self, "search_icon_label"):
            if self._is_glass_theme():
                photo = self._make_icon_photo("search", colors.get("icon", colors["fg"]), 19)
                if photo is not None:
                    self.search_icon_label.configure(text="", image=photo)
                    self.search_icon_label._minirss_image = photo
                else:
                    self.search_icon_label.configure(image="", text=self._glyph("search"), font=self.icon_font)
            else:
                self.search_icon_label.configure(image="", text=self._glyph("search"), font=self.icon_font)
                self.search_icon_label._minirss_image = None
        if hasattr(self, "logo"):
            if self._is_glass_theme():
                photo = self._make_icon_photo("rss", colors["accent"], 34)
                if photo is not None:
                    self.logo.configure(image=photo, text="", bg=colors["accent_soft"],
                                         padx=13, pady=8)
                    self.logo._minirss_image = photo
                else:
                    self.logo.configure(image="", text=self._glyph("rss"), bg=colors["accent_soft"],
                                        fg=colors["accent"], font=(self.icon_font[0], 20), padx=14, pady=9)
            else:
                self.logo.configure(image="", text=self._glyph("rss"), bg=colors["accent"],
                                    fg="#ffffff", font=(self.icon_font[0], 19), padx=12, pady=8)
                self.logo._minirss_image = None
        if hasattr(self, "ios_dock"):
            self._apply_theme_layout()
        self._refresh_glass_surfaces()

    def _change_theme(self, value: str):
        if value not in THEMES:
            return
        self.theme_var.set(value)
        self._style()
        self._apply_theme_layout()
        self._save_settings()

    def _apply_theme_layout(self):
        """Switch between the existing sidebar layout and the Liquid Glass dock."""
        if not hasattr(self, "sidebar") or not hasattr(self, "ios_dock"):
            return
        if self.compact_mode:
            self.ios_dock.pack_forget()
            return

        if self.theme_var.get() == "iOS 27 · Liquid Glass":
            self.sidebar.pack_forget()
            self.main_content.pack_configure(padx=(0, 0))
            self.outer.configure(padding=(22, 16, 22, 14))
            if not self.ios_dock.winfo_manager():
                self.ios_dock.pack(fill="x", pady=(14, 3), padx=160)
            self.root.geometry("1080x820")
            self.root.minsize(820, 620)
        else:
            self.ios_dock.pack_forget()
            if not self.sidebar.winfo_manager():
                self.sidebar.pack(side="left", fill="y", before=self.main_content)
            self.main_content.pack_configure(padx=(12, 0))
            self.outer.configure(padding=(18, 14, 18, 14))
            self.root.geometry("980x760")
            self.root.minsize(760, 560)

    def _open_github_repo(self):
        try:
            repository = normalize_github_repo(self.github_repo_var.get())
        except ValueError as exc:
            messagebox.showwarning("GitHub", str(exc), parent=self.root)
            return
        webbrowser.open(f"https://github.com/{repository}")

    def _open_settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Настройки MiniRSS")
        dialog.resizable(False, True)
        dialog.transient(self.root)
        colors = self._palette()
        dialog.configure(bg=colors["bg"])
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Настройки", style="Header.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"MiniRSS {APP_VERSION} · Windows 10 / 11", style="Sub.TLabel").pack(anchor="w", pady=(0, 15))

        ttk.Label(frame, text="Оформление", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        theme_combo = ttk.Combobox(frame, state="readonly", values=list(THEMES), textvariable=self.theme_var, width=25)
        theme_combo.pack(fill="x", pady=(5, 10))

        glass_options = ttk.LabelFrame(frame, text="Liquid Glass", style="GlassOptions.TLabelframe",
                                       padding=(12, 8))
        appearance_row = ttk.Frame(glass_options, style="Card.TFrame")
        appearance_row.pack(fill="x", pady=(0, 7))
        ttk.Label(appearance_row, text="Внешний вид", style="Panel.TLabel").pack(side="left")
        ttk.Radiobutton(appearance_row, text="Светлый", value="Светлая",
                        variable=self.glass_appearance_var, style="Glass.TRadiobutton",
                        command=lambda: self._change_glass_appearance(self.glass_appearance_var.get())).pack(side="right", padx=(8, 0))
        ttk.Radiobutton(appearance_row, text="Тёмный", value="Тёмная",
                        variable=self.glass_appearance_var, style="Glass.TRadiobutton",
                        command=lambda: self._change_glass_appearance(self.glass_appearance_var.get())).pack(side="right")
        effect_row = ttk.Frame(glass_options, style="Card.TFrame")
        effect_row.pack(fill="x")
        ttk.Label(effect_row, text="Эффект", style="Panel.TLabel").pack(side="left")
        ttk.Radiobutton(effect_row, text="Прозрачный", value="Прозрачный",
                        variable=self.glass_effect_var, style="Glass.TRadiobutton",
                        command=lambda: self._change_glass_effect(self.glass_effect_var.get())).pack(side="right", padx=(8, 0))
        ttk.Radiobutton(effect_row, text="Однотонный", value="Однотонный",
                        variable=self.glass_effect_var, style="Glass.TRadiobutton",
                        command=lambda: self._change_glass_effect(self.glass_effect_var.get())).pack(side="right")
        ttk.Label(glass_options,
                  text="Прозрачный показывает больше фонового слоя. Однотонный делает панели спокойнее и повышает контраст.",
                  style="CardSub.TLabel", wraplength=430, justify="left").pack(anchor="w", pady=(8, 0))

        opacity_title = ttk.Frame(frame)
        opacity_title.pack(fill="x")

        def update_theme_controls(_event=None):
            self._change_theme(self.theme_var.get())
            dialog.configure(bg=self._palette()["bg"])
            if self._is_glass_theme():
                if not glass_options.winfo_manager():
                    glass_options.pack(fill="x", pady=(0, 14), before=opacity_title)
            else:
                glass_options.pack_forget()

        theme_combo.bind("<<ComboboxSelected>>", update_theme_controls)
        if self._is_glass_theme():
            glass_options.pack(fill="x", pady=(0, 14), before=opacity_title)
        ttk.Label(opacity_title, text="Прозрачность окна").pack(side="left")
        opacity_label = ttk.Label(opacity_title, text=f"{round(self.opacity_var.get()*100)}%", style="Sub.TLabel")
        opacity_label.pack(side="right")

        def change_opacity(value):
            self._apply_opacity(value)
            opacity_label.configure(text=f"{round(float(value))}%")
            self._save_settings()

        opacity_scale = ttk.Scale(frame, from_=60, to=100, orient="horizontal", command=change_opacity)
        opacity_scale.set(round(self.opacity_var.get() * 100))
        opacity_scale.pack(fill="x", pady=(6, 14))
        ttk.Checkbutton(frame, text="Поверх остальных окон", variable=self.always_on_top_var,
                        command=self._on_topmost_change).pack(anchor="w", pady=(0, 13))

        ttk.Separator(frame).pack(fill="x", pady=(2, 12))
        ttk.Label(frame, text="Запуск и уведомления", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 7))
        ttk.Checkbutton(frame, text="Запускать MiniRSS вместе с Windows", variable=self.autostart_var,
                        command=self._set_autostart).pack(anchor="w", pady=2)
        ttk.Checkbutton(frame, text="Сворачивать окно в системный трей при закрытии", variable=self.close_to_tray_var,
                        command=self._save_settings).pack(anchor="w", pady=2)
        ttk.Checkbutton(frame, text="Показывать уведомления о новых публикациях", variable=self.notifications_var,
                        command=self._save_settings).pack(anchor="w", pady=2)

        ttk.Separator(frame).pack(fill="x", pady=(13, 12))
        ttk.Label(frame, text="Обновления через GitHub", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        ttk.Label(frame, text="Публичный репозиторий в формате владелец/название:", style="Sub.TLabel").pack(anchor="w")
        update_entry = ttk.Entry(frame, textvariable=self.github_repo_var, width=52)
        update_entry.pack(fill="x", pady=(5, 6))
        ttk.Label(frame, text="Например: alex/minirss. Приложение проверяет опубликованные Releases.",
                  style="Sub.TLabel", wraplength=430).pack(anchor="w", pady=(0, 7))
        ttk.Checkbutton(frame, text="Автоматически проверять обновления раз в сутки", variable=self.auto_check_updates_var,
                        command=self._save_settings).pack(anchor="w", pady=(0, 8))
        update_buttons = ttk.Frame(frame)
        update_buttons.pack(fill="x")
        ttk.Button(update_buttons, text="Проверить обновления", command=lambda: (self._save_settings(), self._check_for_updates(silent=False)),
                   style="Accent.TButton").pack(side="left")
        ttk.Button(update_buttons, text="Открыть GitHub", command=self._open_github_repo).pack(side="left", padx=(8, 0))
        update_entry.bind("<FocusOut>", lambda _e: self._save_settings())
        update_entry.bind("<Return>", lambda _e: (self._save_settings(), self._check_for_updates(silent=False)))
        ttk.Label(frame, text="Обновление скачивается из GitHub Releases с проверкой SHA-256.\nПодписки, избранное и настройки сохраняются.",
                  style="Sub.TLabel", justify="left", wraplength=460).pack(anchor="w", pady=(8, 0))

        ttk.Label(frame, text="Настройки сохраняются автоматически.", style="Sub.TLabel").pack(anchor="w", pady=(14, 0))
        ttk.Button(frame, text="Готово", command=dialog.destroy, style="Accent.TButton").pack(anchor="e", pady=(13, 0))
        dialog.update_idletasks()
        dialog.geometry(f"{max(510, dialog.winfo_reqwidth())}x{dialog.winfo_reqheight()}+{self.root.winfo_rootx()+55}+{self.root.winfo_rooty()+35}")

    # ------------------------------ System tray -----------------------------
    def _start_tray(self):
        if pystray is None or Image is None or ImageDraw is None:
            self.tray_available = False
            return
        try:
            icon_image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            pixels = icon_image.load()
            for y in range(64):
                for x in range(64):
                    t = (x + y) / 126
                    pixels[x, y] = (int(42 + 34 * t), int(105 + 42 * t), int(226 + 18 * t), 255)
            draw = ImageDraw.Draw(icon_image)
            draw.rounded_rectangle((1, 1, 62, 62), radius=16, outline=(255, 255, 255, 100), width=2)
            draw.ellipse((12, 44, 20, 52), fill="white")
            draw.arc((10, 33, 34, 57), start=270, end=360, fill="white", width=5)
            draw.arc((10, 15, 53, 57), start=270, end=360, fill="white", width=5)
            menu = pystray.Menu(
                pystray.MenuItem("Открыть MiniRSS", lambda _icon, _item: self.root.after(0, self._show_from_tray), default=True),
                pystray.MenuItem("Обновить ленты", lambda _icon, _item: self.root.after(0, self._refresh_selected)),
                pystray.MenuItem("Проверить обновления", lambda _icon, _item: self.root.after(0, lambda: self._check_for_updates(False))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Выход", lambda _icon, _item: self.root.after(0, self._exit_app)),
            )
            self.tray_icon = pystray.Icon(APP_NAME, icon_image, f"MiniRSS {APP_VERSION}", menu)
            self.tray_icon.run_detached()
            self.tray_available = True
        except Exception:
            self.tray_icon = None
            self.tray_available = False

    def _show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    def _tray_notify(self, title: str, message: str):
        if not self.tray_icon:
            return
        try:
            self.tray_icon.notify(message, title)
        except Exception:
            pass

    def _notify(self, title: str, message: str):
        if not self.notifications_var.get():
            return
        try:
            if Notification is not None:
                Notification(app_id="MiniRSS", title=title, msg=message, duration="short").show()
            else:
                self._tray_notify(title, message)
        except Exception:
            self._tray_notify(title, message)

    # ---------------------------- Online updating ---------------------------
    def _scheduled_update_check(self):
        if self.auto_check_updates_var.get() and self.github_repo_var.get().strip():
            self._check_for_updates(silent=True)
        self.root.after(UPDATE_CHECK_INTERVAL_MS, self._scheduled_update_check)

    def _check_for_updates(self, silent: bool = False):
        self._save_settings()
        repository = self.github_repo_var.get().strip()
        if not repository:
            if not silent:
                messagebox.showinfo(
                    "Обновления MiniRSS",
                    "Укажите публичный GitHub-репозиторий в настройках, например username/minirss.\n\n"
                    "После первой публикации GitHub Release приложение сможет находить и устанавливать обновления автоматически.",
                    parent=self.root,
                )
            return
        if self.update_check_busy or self.update_download_busy:
            if not silent:
                self.status_var.set("Проверка или установка обновления уже выполняется…")
            return
        self.update_check_busy = True
        self.status_var.set("Проверяем GitHub Releases…")

        def worker():
            try:
                release = fetch_github_release(repository)
                self.events.put(("update_check_done", release, silent, None))
            except Exception as exc:
                self.events.put(("update_check_done", None, silent, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_update_check(self, manifest: dict | None, silent: bool, error: str | None):
        self.update_check_busy = False
        if error:
            self.status_var.set("Не удалось проверить обновления")
            if not silent:
                messagebox.showerror("Проверка обновлений", error, parent=self.root)
            return
        try:
            available = version_tuple(manifest["version"]) > version_tuple(APP_VERSION)
        except (KeyError, ValueError):
            available = False
        if not available:
            self.status_var.set(f"Установлена последняя версия MiniRSS {APP_VERSION}")
            if not silent:
                messagebox.showinfo("Обновления MiniRSS", f"У вас актуальная версия {APP_VERSION}.", parent=self.root)
            return
        self.status_var.set(f"Доступно обновление MiniRSS {manifest['version']}")
        notes = manifest.get("notes", "")
        prompt = f"Доступна новая версия MiniRSS {manifest['version']} (установлена {APP_VERSION})."
        if notes:
            prompt += f"\n\nЧто нового:\n{notes}"
        if manifest.get("html_url"):
            prompt += f"\n\nРелиз: {manifest['html_url']}"
        prompt += "\n\nСкачать и установить обновление сейчас?"
        if silent:
            self._notify("Доступно обновление MiniRSS", f"Версия {manifest['version']}. Откройте настройки для установки.")
            return
        if messagebox.askyesno("Доступно обновление", prompt, parent=self.root):
            self._start_update_download(manifest)

    def _start_update_download(self, manifest: dict):
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                "Обновление EXE",
                "Установка поверх приложения работает в собранной версии MiniRSS.exe.\n"
                "Сейчас запущен исходный Python-файл.",
                parent=self.root,
            )
            return
        if self.update_download_busy:
            return
        self.update_download_busy = True
        self.status_var.set(f"Скачиваем MiniRSS {manifest['version']}…")

        def worker():
            try:
                folder, new_exe = download_update_package(manifest)
                self.events.put(("update_download_done", folder, new_exe, None))
            except Exception as exc:
                self.events.put(("update_download_done", None, None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_update_helper(self, temp_folder: str, package_path: str):
        target_exe = str(Path(sys.executable).resolve())
        helper_path = Path(temp_folder) / "apply_update.ps1"
        use_installer = Path(package_path).name.lower().startswith("minirss_setup")
        helper_path.write_text(build_update_helper_script(), encoding="utf-8-sig")
        creation_flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", str(helper_path), "-ProcessId", str(os.getpid()), "-Package", package_path,
             "-Target", target_exe, "-TempDir", temp_folder, "-UseInstaller", str(use_installer)],
            creationflags=creation_flags,
            close_fds=True,
        )
        self.status_var.set("Обновление подготовлено. Дождитесь завершения установки…")
        self.root.after(500, self._exit_app)


    # ---------------------------------- UI -----------------------------------
    def _build_ui(self):
        self.outer = ttk.Frame(self.root, padding=(18, 14, 18, 14))
        self.outer.pack(fill="both", expand=True)

        self.header = ttk.Frame(self.outer, style="GlassHeader.TFrame", padding=(16, 11))
        self.header.pack(fill="x", pady=(0, 15))
        self._attach_glass_surface(self.header, "header")
        brand = ttk.Frame(self.header, style="GlassHeader.TFrame")
        brand.pack(side="left", fill="x", expand=True)
        self.logo = tk.Label(brand, text=self._glyph("rss"), font=(self.icon_font[0], 19),
                             bg=self._palette()["accent"], fg="#ffffff", padx=12, pady=8)
        self.logo.pack(side="left", padx=(0, 11))
        title_area = ttk.Frame(brand, style="GlassHeader.TFrame")
        title_area.pack(side="left", fill="x", expand=True)
        ttk.Label(title_area, text="MiniRSS", style="Header.TLabel").pack(anchor="w")
        ttk.Label(title_area, text="Твои новости в одном месте", style="Sub.TLabel").pack(anchor="w", pady=(0, 1))
        actions = ttk.Frame(self.header, style="GlassHeader.TFrame")
        actions.pack(side="right")
        self.refresh_button = self._icon_button(actions, GLYPHS["refresh"], "Обновить ленты", self._refresh_selected)
        self.refresh_button.pack(side="left", padx=(4, 0))
        self.add_button = self._icon_button(actions, GLYPHS["add"], "Добавить RSS-ленту", self._add_feed)
        self.add_button.pack(side="left", padx=(4, 0))
        self.presets_button = self._icon_button(actions, GLYPHS["sources"], "Готовые источники новостей", self._add_presets)
        self.presets_button.pack(side="left", padx=(4, 0))
        self.compact_button = self._icon_button(actions, GLYPHS["compact"], "Компактный режим", self._toggle_compact)
        self.compact_button.pack(side="left", padx=(4, 0))
        self.settings_button = self._icon_button(actions, GLYPHS["settings"], "Настройки", self._open_settings)
        self.settings_button.pack(side="left", padx=(4, 0))

        self.main_row = ttk.Frame(self.outer)
        self.main_row.pack(fill="both", expand=True)

        self.sidebar = ttk.Frame(self.main_row, style="Sidebar.TFrame", padding=(7, 12))
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.sidebar.configure(width=64)
        self.nav_buttons = {}
        self.nav_buttons["all"] = self._icon_button(self.sidebar, GLYPHS["home"], "Все новости",
                                                      lambda: self._select_navigation_filter(ALL_FEEDS), "Nav.TButton", 3)
        self.nav_buttons["all"].pack(fill="x", pady=(0, 6))
        self.nav_buttons["favorites"] = self._icon_button(self.sidebar, GLYPHS["favorite"], "Избранное",
                                                            lambda: self._select_navigation_filter(FAVORITES_FILTER), "Nav.TButton", 3)
        self.nav_buttons["favorites"].pack(fill="x", pady=(0, 6))
        self.nav_buttons["sources"] = self._icon_button(self.sidebar, GLYPHS["sources"], "Подборка RSS-источников",
                                                          self._add_presets, "Nav.TButton", 3)
        self.nav_buttons["sources"].pack(fill="x", pady=(0, 6))
        ttk.Separator(self.sidebar).pack(fill="x", pady=(8, 8))
        self.nav_buttons["add"] = self._icon_button(self.sidebar, GLYPHS["add"], "Добавить ленту",
                                                      self._add_feed, "Nav.TButton", 3)
        self.nav_buttons["add"].pack(fill="x", pady=(0, 6))
        ttk.Frame(self.sidebar, style="Sidebar.TFrame").pack(fill="both", expand=True)
        self.nav_buttons["settings"] = self._icon_button(self.sidebar, GLYPHS["settings"], "Настройки",
                                                           self._open_settings, "Nav.TButton", 3)
        self.nav_buttons["settings"].pack(fill="x", side="bottom")

        self.main_content = ttk.Frame(self.main_row, style="Card.TFrame", padding=16)
        self.main_content.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self._attach_glass_surface(self.main_content, "content")

        self.controls = ttk.Frame(self.main_content, style="Card.TFrame")
        self._attach_glass_surface(self.controls, "controls")
        self.controls.pack(fill="x", pady=(0, 11))
        ttk.Label(self.controls, text="Лента", style="Panel.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 10))
        self.feed_combo = ttk.Combobox(self.controls, textvariable=self.filter_var, state="readonly")
        self.feed_combo.pack(side="left", fill="x", expand=True)
        self.feed_combo.bind("<<ComboboxSelected>>", lambda _e: (self._render_articles(), self._update_nav_state()))
        self.remove_feed_button = self._icon_button(self.controls, GLYPHS["delete"], "Удалить выбранную ленту", self._remove_feed)
        self.remove_feed_button.pack(side="left", padx=(7, 0))

        self.search_frame = ttk.Frame(self.main_content, style="Card.TFrame")
        self._attach_glass_surface(self.search_frame, "search")
        self.search_frame.pack(fill="x", pady=(0, 11))
        self.search_icon_label = ttk.Label(self.search_frame, text=self._glyph("search"),
                                           font=self.icon_font, style="Panel.TLabel")
        self.search_icon_label.pack(side="left", padx=(3, 8))
        search_entry = ttk.Entry(self.search_frame, textvariable=self.search_var)
        search_entry.pack(fill="x", expand=True, side="left")
        search_entry.bind("<KeyRelease>", lambda _e: self._render_articles())

        self.list_frame = ttk.Frame(self.main_content, style="Card.TFrame")
        self.list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(self.list_frame, columns=("feed", "date"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Заголовок", anchor="w")
        self.tree.heading("feed", text="Источник", anchor="w")
        self.tree.heading("date", text="Дата", anchor="e")
        self.tree.column("#0", width=500, minwidth=180, stretch=True)
        self.tree.column("feed", width=170, minwidth=95, stretch=False)
        self.tree.column("date", width=88, minwidth=65, stretch=False, anchor="e")
        scrollbar = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_article_select)
        self.tree.bind("<Double-1>", lambda _e: self._open_article())

        self.detail_card = ttk.Frame(self.main_content, style="Detail.TFrame", padding=(13, 11))
        self.detail_card.pack(fill="x", pady=(12, 0))
        self._attach_glass_surface(self.detail_card, "detail")
        self.detail_title = ttk.Label(self.detail_card, text="Выберите новость", style="Detail.TLabel",
                                      font=("Segoe UI", 11, "bold"), wraplength=720)
        self.detail_title.pack(anchor="w")
        self.detail_source = ttk.Label(self.detail_card, text="", style="DetailSub.TLabel")
        self.detail_source.pack(anchor="w", pady=(2, 7))
        colors = self._palette()
        self.description = tk.Text(self.detail_card, height=4, wrap="word", font=("Segoe UI", 9),
                                   bg=colors["detail"], fg=colors["text_fg"], insertbackground=colors["text_fg"],
                                   relief="flat", padx=2, pady=4, state="disabled", highlightthickness=0)
        self.description.pack(fill="x")
        self.bottom = ttk.Frame(self.detail_card, style="Detail.TFrame")
        self.bottom.pack(fill="x", pady=(8, 0))
        self.open_button = self._icon_button(self.bottom, GLYPHS["open"], "Открыть статью в браузере", self._open_article, width=3)
        self.open_button.pack(side="left")
        self.favorite_button = self._icon_button(self.bottom, GLYPHS["favorite"], "Добавить в избранное", self._toggle_favorite, width=3)
        self.favorite_button.pack(side="left", padx=(6, 0))
        ttk.Label(self.bottom, textvariable=self.status_var, style="DetailSub.TLabel").pack(side="right", padx=(8, 0))

        self.compact_bar = ttk.Frame(self.main_content, style="Card.TFrame")
        ttk.Label(self.compact_bar, text=self._glyph("rss"), font=self.icon_font, style="Panel.TLabel").pack(side="left", padx=(1, 7))
        ttk.Label(self.compact_bar, text="MiniRSS", style="Panel.TLabel", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 8))
        self._icon_button(self.compact_bar, GLYPHS["refresh"], "Обновить", self._refresh_selected).pack(side="left", padx=(0, 3))
        self.compact_favorite_button = self._icon_button(self.compact_bar, GLYPHS["favorite"], "Добавить в избранное", self._toggle_favorite)
        self.compact_favorite_button.pack(side="left", padx=(0, 3))
        self._icon_button(self.compact_bar, GLYPHS["expand"], "Развернуть окно", lambda: self._set_compact_mode(False)).pack(side="right")

        # Horizontal floating dock used only by the separate Liquid Glass theme.
        self.ios_dock = ttk.Frame(self.outer, style="Dock.TFrame", padding=(10, 7))
        self._attach_glass_surface(self.ios_dock, "dock")
        self.ios_nav_buttons = {}
        dock_actions = (
            ("all", GLYPHS["home"], "Все новости", lambda: self._select_navigation_filter(ALL_FEEDS)),
            ("favorites", GLYPHS["favorite"], "Избранное", lambda: self._select_navigation_filter(FAVORITES_FILTER)),
            ("sources", GLYPHS["sources"], "Готовые источники", self._add_presets),
            ("settings", GLYPHS["settings"], "Настройки", self._open_settings),
        )
        for key, glyph, tooltip, command in dock_actions:
            button = self._icon_button(self.ios_dock, glyph, tooltip, command, "Dock.TButton", 7)
            button.pack(side="left", fill="x", expand=True, padx=5)
            self.ios_nav_buttons[key] = button
        self._update_nav_state()

    def _select_navigation_filter(self, selection: str):
        self.filter_var.set(selection)
        self._render_articles()
        self._update_nav_state()

    def _update_nav_state(self):
        if not hasattr(self, "nav_buttons"):
            return
        selected = self.filter_var.get()
        active = "favorites" if selected == FAVORITES_FILTER else ("all" if selected == ALL_FEEDS else None)
        for key, button in self.nav_buttons.items():
            style_name = "NavActive.TButton" if key == active else "Nav.TButton"
            try:
                button.configure(style=style_name)
            except tk.TclError:
                pass
        for key, button in getattr(self, "ios_nav_buttons", {}).items():
            style_name = "DockActive.TButton" if key == active else "Dock.TButton"
            try:
                button.configure(style=style_name)
            except tk.TclError:
                pass
        self._refresh_icon_buttons()

    def _set_compact_mode(self, enabled: bool, save: bool = True):
        self.compact_mode = bool(enabled)
        self.header.pack_forget()
        self.sidebar.pack_forget()
        for widget in (self.controls, self.search_frame, self.detail_card):
            widget.pack_forget()
        self.compact_bar.pack_forget()

        if self.compact_mode:
            self.main_content.configure(padding=8)
            self.compact_bar.pack(fill="x", pady=(0, 6), before=self.list_frame)
            self.search_var.set("")
            self.tree.configure(show="tree", displaycolumns=())
            self.root.geometry("390x450")
            self.root.minsize(300, 260)
            self.always_on_top_var.set(True)
            self._apply_topmost()
        else:
            self.main_content.configure(padding=16)
            self.header.pack(fill="x", pady=(0, 15), before=self.main_row)
            self.sidebar.pack(side="left", fill="y")
            self.main_content.pack(side="left", fill="both", expand=True, padx=(12, 0))
            self.controls.pack(fill="x", pady=(0, 11), before=self.list_frame)
            self.search_frame.pack(fill="x", pady=(0, 11), before=self.list_frame)
            self.detail_card.pack(fill="x", pady=(12, 0))
            self.tree.configure(show="tree headings", displaycolumns=("feed", "date"))
            self.root.geometry("980x760")
            self.root.minsize(760, 560)
        self._apply_theme_layout()
        self._render_articles()
        if save:
            self._save_settings()

    def _toggle_compact(self):
        self._set_compact_mode(not self.compact_mode)

    # ------------------------------- Persistence -----------------------------
    def _load_feeds(self):
        try:
            if DATA_FILE.exists():
                raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    self.feeds = [f for f in raw if isinstance(f, dict) and f.get("url") and f.get("id")]
        except (OSError, json.JSONDecodeError):
            messagebox.showwarning("Настройки", "Не удалось прочитать файл подписок. Будет создан новый список.", parent=self.root)
            self.feeds = []

    def _save_feeds(self):
        try:
            DATA_FILE.write_text(json.dumps(self.feeds, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Не удалось сохранить", str(exc), parent=self.root)

    def _load_favorites(self):
        try:
            if FAVORITES_FILE.exists():
                raw = json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, dict) and (item.get("link") or item.get("title")):
                            self.favorites[article_key(item)] = item
        except (OSError, json.JSONDecodeError):
            self.favorites = {}

    def _save_favorites(self):
        try:
            FAVORITES_FILE.write_text(json.dumps(list(self.favorites.values()), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.status_var.set(f"Не удалось сохранить избранное: {exc}")

    def _render_feed_filter(self):
        previous = self.filter_var.get()
        values = [ALL_FEEDS, FAVORITES_FILTER]
        self.filter_map = {ALL_FEEDS: "__all__", FAVORITES_FILTER: "__favorites__"}
        seen: dict[str, int] = {}
        for feed in self.feeds:
            title = feed.get("title", "RSS")
            seen[title] = seen.get(title, 0) + 1
            label = title if seen[title] == 1 else f"{title} ({seen[title]})"
            values.append(label)
            self.filter_map[label] = feed["id"]
        self.feed_combo["values"] = values
        if previous in values:
            self.filter_var.set(previous)
        else:
            self.filter_var.set(ALL_FEEDS)
        self._update_nav_state()

    # --------------------------------- Feeds ---------------------------------
    def _add_feed(self):
        dialog = AddFeedDialog(self.root)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        if any(f.get("url", "").rstrip("/") == dialog.result["url"].rstrip("/") for f in self.feeds):
            messagebox.showinfo("Уже добавлено", "Эта RSS-лента уже есть в списке.", parent=self.root)
            return
        self.feeds.append(dialog.result)
        self._save_feeds()
        self._render_feed_filter()
        self.filter_var.set(next(label for label, feed_id in self.filter_map.items() if feed_id == dialog.result["id"]))
        self._refresh_feeds([dialog.result])

    def _add_presets(self):
        dialog = PresetFeedsDialog(self.root, PRESET_FEEDS)
        self.root.wait_window(dialog)
        if not dialog.result:
            return
        existing = {f.get("url", "").rstrip("/") for f in self.feeds}
        added = []
        skipped = 0
        for feed in dialog.result:
            if feed["url"].rstrip("/") in existing:
                skipped += 1
                continue
            cleaned = {k: feed[k] for k in ("id", "title", "url")}
            self.feeds.append(cleaned)
            added.append(cleaned)
            existing.add(feed["url"].rstrip("/"))
        if not added:
            messagebox.showinfo("Источники", "Все выбранные источники уже есть в подписках.", parent=self.root)
            return
        self._save_feeds()
        self._render_feed_filter()
        self.filter_var.set(ALL_FEEDS)
        self.status_var.set(f"Добавлено источников: {len(added)}" + (f", уже были: {skipped}" if skipped else ""))
        self._refresh_feeds(added)

    def _remove_feed(self):
        selected = self.filter_var.get()
        feed_id = self.filter_map.get(selected)
        if not feed_id or feed_id in ("__all__", "__favorites__"):
            messagebox.showinfo("Удаление", "Сначала выберите конкретную ленту в списке.", parent=self.root)
            return
        feed = next((f for f in self.feeds if f.get("id") == feed_id), None)
        if not feed:
            return
        title = feed.get("title", "RSS")
        if messagebox.askyesno("Удалить ленту", f"Удалить подписку «{title}»?\nСохранённые статьи в избранном останутся.", parent=self.root):
            self.feeds.remove(feed)
            self.articles = [a for a in self.articles if a.get("feed_id") != feed_id]
            self._save_feeds()
            self.filter_var.set(ALL_FEEDS)
            self._render_feed_filter()
            self._render_articles()
            self.status_var.set("Лента удалена")

    def _refresh_selected(self, silent: bool = False):
        if not self.feeds:
            self.status_var.set("Добавьте RSS-ссылку или выберите готовые источники")
            self._render_articles()
            return
        selected = self.filter_var.get()
        feed_id = self.filter_map.get(selected)
        if selected == FAVORITES_FILTER:
            feeds = self.feeds
        elif feed_id in (None, "__all__"):
            feeds = self.feeds
        else:
            feeds = [f for f in self.feeds if f.get("id") == feed_id]
        self._refresh_feeds(feeds, silent=silent)

    def _refresh_feeds(self, feeds: list[dict], silent: bool = False):
        if self.busy:
            if not silent:
                self.status_var.set("Обновление уже выполняется…")
            return
        if not feeds:
            return
        self.busy = True
        self.status_var.set(f"Обновление: 0/{len(feeds)}…")
        feeds_snapshot = [dict(feed) for feed in feeds]

        def worker():
            results = []
            for feed in feeds_snapshot:
                try:
                    title, items = fetch_feed(feed["url"], feed.get("title", "RSS"))
                    results.append((feed["id"], title, items, None))
                except Exception as exc:
                    results.append((feed["id"], feed.get("title", "RSS"), [], str(exc)))
                self.events.put(("progress", len(results), len(feeds_snapshot)))
            self.events.put(("done", results, silent))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    self.status_var.set(f"Обновление: {event[1]}/{event[2]}…")
                elif event[0] == "done":
                    self._apply_refresh(event[1], event[2])
                elif event[0] == "update_check_done":
                    self._handle_update_check(event[1], event[2], event[3])
                elif event[0] == "update_download_done":
                    self.update_download_busy = False
                    if event[3]:
                        self.status_var.set("Не удалось скачать обновление")
                        messagebox.showerror("Обновление MiniRSS", event[3], parent=self.root)
                    else:
                        try:
                            self._launch_update_helper(event[1], event[2])
                        except Exception as exc:
                            messagebox.showerror("Не удалось запустить установщик обновления", str(exc), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(150, self._poll_events)

    def _apply_refresh(self, results: list, silent: bool):
        self.busy = False
        successful = 0
        errors = []
        new_articles: list[dict] = []
        by_id = {feed.get("id"): feed for feed in self.feeds}
        for feed_id, title, items, error in results:
            feed = by_id.get(feed_id)
            if not feed:
                continue
            if error:
                errors.append(f"{feed.get('title', title)}: {error}")
                feed["error"] = error
                continue
            successful += 1
            feed["title"] = title or feed.get("title", "RSS")
            feed["error"] = ""
            feed["updated"] = datetime.now().strftime("%d.%m.%Y %H:%M")
            known_keys = set(feed.get("seen_keys", []))
            initialized = bool(feed.get("seen_initialized", False))
            if initialized:
                new_articles.extend(article for article in items if article_key(article) not in known_keys)
            current_keys = [article_key(article) for article in items]
            feed["seen_keys"] = list(dict.fromkeys(current_keys + list(known_keys)))[:500]
            feed["seen_initialized"] = True
            for article in items:
                article["feed_id"] = feed_id
                article["feed_title"] = feed["title"]
                key = article_key(article)
                if key in self.favorites:
                    saved = self.favorites[key]
                    saved.update({k: article.get(k) for k in ("title", "link", "summary", "date", "timestamp", "feed_id", "feed_title")})
            self.articles = [a for a in self.articles if a.get("feed_id") != feed_id]
            self.articles.extend(items)
        self.articles.sort(key=lambda a: a.get("timestamp", 0), reverse=True)
        self._save_feeds()
        self._save_favorites()
        self._render_feed_filter()
        self._render_articles()
        if new_articles:
            first_titles = [a.get("title", "Без названия") for a in new_articles[:3]]
            message = f"Новых публикаций: {len(new_articles)}"
            if first_titles:
                message += "\n" + "\n".join(f"• {title[:90]}" for title in first_titles)
            self._notify("Новые публикации MiniRSS", message)
        if errors:
            self.status_var.set(f"Обновлено лент: {successful}. Ошибок: {len(errors)}")
            if not silent:
                first = errors[0]
                messagebox.showwarning("Некоторые ленты недоступны", first + ("\n…" if len(errors) > 1 else ""), parent=self.root)
        else:
            self.status_var.set(f"Обновлено: {successful} лент · {len(self.articles)} новостей")

    # ------------------------------- Articles --------------------------------
    def _render_articles(self):
        selected = self.filter_var.get()
        query = self.search_var.get().strip().lower()
        if selected == FAVORITES_FILTER:
            source = list(self.favorites.values())
        elif selected == ALL_FEEDS or self.filter_map.get(selected) == "__all__":
            source = self.articles
        else:
            feed_id = self.filter_map.get(selected)
            source = [a for a in self.articles if a.get("feed_id") == feed_id]
        if query:
            source = [a for a in source if query in a.get("title", "").lower() or query in a.get("summary", "").lower()]
        source.sort(key=lambda a: a.get("timestamp", 0), reverse=True)
        self.filtered_articles = source
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, article in enumerate(source):
            stamp = article.get("timestamp", 0)
            try:
                date_text = datetime.fromtimestamp(stamp).strftime("%d.%m") if stamp else ""
            except (ValueError, OSError, OverflowError):
                date_text = ""
            display_title = ("★ " if article_key(article) in self.favorites else "") + article.get("title", "Без названия")
            self.tree.insert("", "end", iid=str(index), text=display_title,
                             values=(article.get("feed_title", ""), date_text))
        self._show_article(None)
        if selected == FAVORITES_FILTER and not source:
            self.detail_title.configure(text="Избранное пока пусто")
            self.detail_source.configure(text="Выберите новость и нажмите «В избранное».")
        elif not source and not self.feeds:
            self.detail_title.configure(text="Здесь появятся ваши новости")
            self.detail_source.configure(text="Нажмите «Источники» или «＋ Лента», чтобы добавить подписки.")
        elif not source:
            self.detail_title.configure(text="Новостей пока нет")
            self.detail_source.configure(text="Нажмите «Обновить» или проверьте адрес ленты.")
        self._update_favorite_buttons()

    def _on_article_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        try:
            article = self.filtered_articles[int(selection[0])]
        except (ValueError, IndexError):
            return
        self._show_article(article)

    def _show_article(self, article: dict | None):
        self.current_article = article
        if article is None:
            self.detail_title.configure(text="Выберите новость")
            self.detail_source.configure(text="")
            self.open_button.configure(state="disabled")
            self._set_icon_button_symbol(self.favorite_button, "favorite")
            self._set_icon_button_symbol(self.compact_favorite_button, "favorite")
            self.favorite_button.configure(state="disabled")
            self.compact_favorite_button.configure(state="disabled")
            text = ""
        else:
            self.detail_title.configure(text=article.get("title", "Без названия"))
            date_text = article.get("date", "")
            self.detail_source.configure(text=f"{article.get('feed_title', '')}  ·  {date_text}".strip(" ·"))
            valid_link = article.get("link", "").startswith(("http://", "https://"))
            self.open_button.configure(state="normal" if valid_link else "disabled")
            self._update_favorite_buttons()
            text = article.get("summary", "") or "Описание для этой новости не предоставлено. Откройте статью, чтобы прочитать её полностью."
        self.description.configure(state="normal")
        self.description.delete("1.0", "end")
        self.description.insert("1.0", text)
        self.description.configure(state="disabled")

    def _is_favorite(self, article: dict | None) -> bool:
        return bool(article and article_key(article) in self.favorites)

    def _update_favorite_buttons(self):
        selected = self.current_article
        if selected is None:
            glyph = self._glyph("favorite")
            self.favorite_button.configure(state="disabled", text=glyph)
            self.compact_favorite_button.configure(state="disabled", text=glyph)
            return
        is_saved = self._is_favorite(selected)
        glyph = self._glyph("favorite_filled") if is_saved else self._glyph("favorite")
        symbol = "favorite_filled" if is_saved else "favorite"
        self._set_icon_button_symbol(self.favorite_button, symbol)
        self._set_icon_button_symbol(self.compact_favorite_button, symbol)
        self.favorite_button.configure(state="normal")
        self.compact_favorite_button.configure(state="normal")

    def _toggle_favorite(self):
        if not self.current_article:
            return
        article = deepcopy(self.current_article)
        key = article_key(article)
        if key in self.favorites:
            del self.favorites[key]
        else:
            self.favorites[key] = article
        self._save_favorites()
        self._render_articles()
        # Keep the current row selected when it remains in the active view.
        for index, candidate in enumerate(self.filtered_articles):
            if article_key(candidate) == key:
                iid = str(index)
                self.tree.selection_set(iid)
                self.tree.see(iid)
                self._show_article(candidate)
                break
        self._update_favorite_buttons()

    def _open_article(self):
        if self.current_article and self.current_article.get("link", "").startswith(("http://", "https://")):
            webbrowser.open(self.current_article["link"])

    # --------------------------------- Other ---------------------------------
    def _auto_refresh(self):
        self._refresh_selected(silent=True)
        self.root.after(REFRESH_INTERVAL_MS, self._auto_refresh)

    def _on_close(self):
        if self.close_to_tray_var.get() and self.tray_available:
            self.root.withdraw()
            self.status_var.set("MiniRSS продолжает работать в системном трее")
            self._tray_notify("MiniRSS работает в фоне", "Нажмите значок MiniRSS в системном трее, чтобы открыть окно")
            return
        self._exit_app()

    def _exit_app(self):
        self._save_feeds()
        self._save_favorites()
        self._save_settings()
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
        self.root.destroy()


def main():
    root = tk.Tk()
    MiniRSSApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
