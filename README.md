# Zaparoo MiSTer Database

Official Zaparoo database for the MiSTer Downloader and Update All.

This database installs the MiSTer Zaparoo stack:

- `Scripts/zaparoo.sh` — Zaparoo Core for MiSTer
- `zaparoo/frontend` — Zaparoo Frontend
- `zaparoo/MiSTer_Zaparoo` — frontend dependency
- `zaparoo/menu_zaparoo.rbf` — frontend dependency

## Install manually

Add this to `/media/fat/downloader.ini`:

```ini
[ZaparooProject/Zaparoo_MiSTer]
db_url = https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/db.json.zip
```

Then run `downloader` or `update_all`.

A drop-in config is also published at:

```text
https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/downloader_ZaparooProject_Zaparoo_MiSTer.zip
```

## How it works

The repository does **not** store Zaparoo binaries.

The GitHub Actions workflow builds a Downloader database that points at the official GitHub release ZIPs from:

- `ZaparooProject/zaparoo-core`
- `ZaparooProject/zaparoo-frontend`

Downloader extracts only the required MiSTer files from those release ZIPs.

## Maintainer notes

The database is rebuilt on every push to `main` and can also be run manually from GitHub Actions.

By default it uses the latest release from both `zaparoo-core` and `zaparoo-frontend`. Manual workflow dispatch supports overriding either release tag.
