#!/usr/bin/env python3
"""Build the Zaparoo MiSTer Downloader database.

This repository intentionally does not store release binaries. The generated
Downloader database points at the canonical GitHub release ZIPs from
zaparoo-core and zaparoo-frontend, then asks Downloader to extract only the
MiSTer files Zaparoo needs.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DB_ID = os.environ["GITHUB_REPOSITORY"]
print(f"DB_ID: {DB_ID}")
DB_URL = "https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/db.json.zip"
CORE_REPO = "ZaparooProject/zaparoo-core"
FRONTEND_REPO = "ZaparooProject/zaparoo-frontend"

CORE_ASSET_RE = re.compile(r"^zaparoo-mister_arm-(?P<version>.+)\.zip$")
FRONTEND_ASSET_RE = re.compile(r"^zaparoo-frontend-(?P<tag>v.+)\.zip$")

CORE_FILES = {
    "Scripts/zaparoo.sh": "zaparoo.sh",
}

FRONTEND_FILES = {
    "zaparoo/frontend": "zaparoo/frontend",
    "zaparoo/MiSTer_Zaparoo": "zaparoo/MiSTer_Zaparoo",
    "zaparoo/menu_zaparoo.rbf": "zaparoo/menu_zaparoo.rbf",
}


@dataclass(frozen=True)
class ReleaseAsset:
    tag: str
    name: str
    url: str


@dataclass(frozen=True)
class FileInfo:
    size: int
    md5: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Zaparoo MiSTer Downloader DB")
    parser.add_argument("--no-push", action="store_true", help="build locally without pushing the db branch")
    parser.add_argument("--skip-test", action="store_true", help="skip downloader_test.py validation")
    parser.add_argument("--core-tag", default=os.getenv("ZAPAROO_CORE_TAG", "latest"))
    parser.add_argument("--frontend-tag", default=os.getenv("ZAPAROO_FRONTEND_TAG", "latest"))
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        core_asset = find_release_asset(CORE_REPO, args.core_tag, CORE_ASSET_RE)
        frontend_asset = find_release_asset(FRONTEND_REPO, args.frontend_tag, FRONTEND_ASSET_RE)

        core_zip = tmp_path / core_asset.name
        frontend_zip = tmp_path / frontend_asset.name
        download(core_asset.url, core_zip)
        download(frontend_asset.url, frontend_zip)

        db = build_db(core_asset, core_zip, frontend_asset, frontend_zip)

    if not args.no_push and not needs_publish(db):
        print("No database changes detected; skipping validation and publish.")
        return 0

    write_outputs(db)

    if not args.skip_test:
        run_downloader_test()

    if not args.no_push:
        publish_outputs()

    return 0


def find_release_asset(repo: str, tag: str, pattern: re.Pattern[str]) -> ReleaseAsset:
    release_url = f"https://api.github.com/repos/{repo}/releases/latest" if tag == "latest" else f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    data = read_json_url(release_url)
    release_tag = data["tag_name"]

    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if pattern.match(name):
            return ReleaseAsset(tag=release_tag, name=name, url=asset["browser_download_url"])

    raise RuntimeError(f"No matching release asset found for {repo}@{release_tag}")


def read_json_url(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Zaparoo_MiSTer DB builder"})
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download(url: str, path: Path) -> None:
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "Zaparoo_MiSTer DB builder"})
    with urllib.request.urlopen(request, timeout=300) as response, path.open("wb") as out:
        shutil.copyfileobj(response, out)


def needs_publish(db: dict[str, Any]) -> bool:
    current_db = read_current_published_db()
    if current_db is None:
        print("No published database found; publishing new database.")
        return True

    if reformat_db_for_comparison(db) == reformat_db_for_comparison(current_db):
        return False

    print("Database changes detected; publishing new database.")
    return True


def read_current_published_db() -> dict[str, Any] | None:
    request = urllib.request.Request(DB_URL, headers={"User-Agent": "Zaparoo_MiSTer DB builder"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return json.loads(archive.read("db.json"))


def reformat_db_for_comparison(db: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(db))
    result.pop("timestamp", None)
    normalize_archives(result)
    return result


def normalize_archives(db: dict[str, Any]) -> None:
    archives = db.get("archives", {})
    for archive in archives.values():
        if "archive_file" in archive and "contents_file" not in archive:
            archive["contents_file"] = archive.pop("archive_file")
        if "summary_inline" in archive and "internal_summary" not in archive:
            archive["internal_summary"] = archive.pop("summary_inline")
        if archive.get("extract") == "selective":
            archive["kind"] = "extract_single_files"
            del archive["extract"]

        summary = archive.get("internal_summary", {})
        for file_desc in summary.get("files", {}).values():
            if "arc_id" in file_desc and "zip_id" not in file_desc:
                file_desc["zip_id"] = file_desc.pop("arc_id")
            if "arc_at" in file_desc and "zip_path" not in file_desc:
                file_desc["zip_path"] = file_desc.pop("arc_at")
        for folder_desc in summary.get("folders", {}).values():
            if "arc_id" in folder_desc and "zip_id" not in folder_desc:
                folder_desc["zip_id"] = folder_desc.pop("arc_id")


def build_db(core_asset: ReleaseAsset, core_zip: Path, frontend_asset: ReleaseAsset, frontend_zip: Path) -> dict[str, Any]:
    core_archive = file_info(core_zip)
    frontend_archive = file_info(frontend_zip)

    print(f"Core release: {core_asset.tag} ({core_asset.name})")
    print(f"Frontend release: {frontend_asset.tag} ({frontend_asset.name})")

    return {
        "v": 1,
        "db_id": DB_ID,
        "timestamp": int(time.time()),
        "files": {},
        "folders": {},
        "archives": {
            "zaparoo_core": {
                "format": "zip",
                "extract": "selective",
                "description": f"Extracting Zaparoo Core {core_asset.tag}",
                "archive_file": {
                    "hash": core_archive.md5,
                    "size": core_archive.size,
                    "url": core_asset.url,
                },
                "summary_inline": build_summary("zaparoo_core", core_zip, CORE_FILES, {"Scripts/"}),
            },
            "zaparoo_frontend": {
                "format": "zip",
                "extract": "selective",
                "description": f"Extracting Zaparoo Frontend {frontend_asset.tag}",
                "archive_file": {
                    "hash": frontend_archive.md5,
                    "size": frontend_archive.size,
                    "url": frontend_asset.url,
                },
                "summary_inline": build_summary("zaparoo_frontend", frontend_zip, FRONTEND_FILES, {"zaparoo/"}),
            },
        },
    }


def build_summary(archive_id: str, zip_path: Path, install_map: dict[str, str], folders: set[str]) -> dict[str, Any]:
    files: dict[str, Any] = {}
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        for install_path, archive_path in install_map.items():
            if archive_path not in names:
                raise RuntimeError(f"{archive_path} missing from {zip_path.name}")
            data = archive.read(archive_path)
            files[install_path] = {
                "hash": hashlib.md5(data).hexdigest(),
                "size": len(data),
                "reboot": True,
                "arc_id": archive_id,
                "arc_at": archive_path,
            }

    return {
        "files": files,
        "folders": {folder: {"arc_id": archive_id} for folder in sorted(folders)},
    }


def file_info(path: Path) -> FileInfo:
    data = path.read_bytes()
    return FileInfo(size=len(data), md5=hashlib.md5(data).hexdigest())


def write_outputs(db: dict[str, Any]) -> None:
    Path("db.json").write_text(json.dumps(db, indent=4, sort_keys=True) + "\n", encoding="utf-8")
    with zipfile.ZipFile("db.json.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.write("db.json")

    ini_name = "downloader_ZaparooProject_Zaparoo_MiSTer.ini"
    ini_contents = f"[{DB_ID}]\ndb_url = {DB_URL}\n"
    Path(ini_name).write_text(ini_contents, encoding="utf-8")
    with zipfile.ZipFile("downloader_ZaparooProject_Zaparoo_MiSTer.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(ini_name, ini_contents)

    print("Wrote db.json, db.json.zip, and drop-in downloader files")


def run_downloader_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        test_path = tmp_path / "downloader_test.py"
        download("https://github.com/MiSTer-devel/Downloader_MiSTer/releases/download/latest/downloader_test.py", test_path)
        test_path.chmod(0o755)
        subprocess.run([sys.executable, str(test_path), DB_ID, str(Path("db.json").resolve())], check=True)


def publish_outputs() -> None:
    for output in [
        "db.json.zip",
        "downloader_ZaparooProject_Zaparoo_MiSTer.ini",
        "downloader_ZaparooProject_Zaparoo_MiSTer.zip",
    ]:
        if not Path(output).exists():
            raise RuntimeError(f"Expected output missing: {output}")

    subprocess.run(["git", "config", "--global", "user.email", "actions@github.com"], check=True)
    subprocess.run(["git", "config", "--global", "user.name", "GitHub Actions"], check=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for output in ["db.json.zip", "downloader_ZaparooProject_Zaparoo_MiSTer.ini", "downloader_ZaparooProject_Zaparoo_MiSTer.zip"]:
            shutil.copy2(output, tmp_path / output)

        subprocess.run(["git", "checkout", "--orphan", "db"], check=True)
        subprocess.run(["git", "reset"], check=True)
        for output in ["db.json.zip", "downloader_ZaparooProject_Zaparoo_MiSTer.ini", "downloader_ZaparooProject_Zaparoo_MiSTer.zip"]:
            shutil.copy2(tmp_path / output, output)
        subprocess.run(["git", "add", "-f", "db.json.zip", "downloader_ZaparooProject_Zaparoo_MiSTer.ini", "downloader_ZaparooProject_Zaparoo_MiSTer.zip"], check=True)
        subprocess.run(["git", "commit", "-m", "Build Zaparoo MiSTer database"], check=True)
        run_with_retries(["git", "push", "--force", "origin", "db"], attempts=3, delay_seconds=15)


def run_with_retries(command: list[str], attempts: int, delay_seconds: int) -> None:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(command, check=True)
            return
        except subprocess.CalledProcessError as error:
            last_error = error
            if attempt == attempts:
                break
            print(f"Command failed on attempt {attempt}/{attempts}: {' '.join(command)}")
            print(f"Retrying in {delay_seconds} seconds...")
            time.sleep(delay_seconds)

    assert last_error is not None
    raise last_error


if __name__ == "__main__":
    raise SystemExit(main())
