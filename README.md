# Zaparoo MiSTer Database

MiSTer Downloader / Update All database for Zaparoo.

It installs:

- `Scripts/zaparoo.sh` — Zaparoo Core for MiSTer
- `zaparoo/frontend` — Zaparoo Frontend
- `zaparoo/MiSTer_Zaparoo` — frontend dependency
- `zaparoo/menu_zaparoo.rbf` — frontend dependency

## Manual install

Add this to `/media/fat/downloader.ini`:

```ini
[ZaparooProject/Zaparoo_MiSTer]
db_url = https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/db.json.zip
```

Then run `downloader` or `update_all`.

There is also a drop-in config ZIP:

```text
https://raw.githubusercontent.com/ZaparooProject/Zaparoo_MiSTer/db/downloader_ZaparooProject_Zaparoo_MiSTer.zip
```

## Binaries

This repo does not mirror Zaparoo binaries.

The workflow builds a Downloader database that points to the official release ZIPs from:

- `ZaparooProject/zaparoo-core`
- `ZaparooProject/zaparoo-frontend`

Downloader extracts the MiSTer files it needs from those ZIPs.

## Maintainer notes

The database rebuilds on pushes to `main`, on a schedule, and when run manually from GitHub Actions.

Manual runs can target specific `zaparoo-core` or `zaparoo-frontend` release tags. Otherwise the workflow uses the latest release from each repo.
