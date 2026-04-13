import argparse
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


DB_PATH = "aquarium.db"
LOCAL_TZ = ZoneInfo("America/Toronto")

DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def normalize_epoch(value):
    epoch = float(value)
    if epoch > 1_000_000_000_000:
        epoch = epoch / 1000
    return int(epoch)


def parse_timestamp(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return normalize_epoch(value)

    text = str(value).strip()
    if not text:
        return None

    try:
        return normalize_epoch(text)
    except ValueError:
        pass

    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        dt = None

    if dt is None:
        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)

    return int(dt.timestamp())


def timestamp_is_clean(value, parsed):
    return isinstance(value, int) and value == parsed


def table_exists(conn):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'temperature_log'"
    ).fetchone()
    return row is not None


def backup_db(db_path):
    backup_path = db_path.with_suffix(
        db_path.suffix + time.strftime(".backup-%Y%m%d-%H%M%S")
    )
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate(db_path, dry_run=False, delete_bad=False):
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"database not found: {db_path}")

    backup_path = None
    if not dry_run:
        backup_path = backup_db(db_path)

    with sqlite3.connect(db_path) as conn:
        if not table_exists(conn):
            raise RuntimeError("temperature_log table does not exist")

        rows = conn.execute("SELECT rowid, ts FROM temperature_log").fetchall()
        updates = []
        bad_rows = []

        for rowid, raw_ts in rows:
            parsed = parse_timestamp(raw_ts)
            if parsed is None:
                bad_rows.append((rowid, raw_ts))
            elif not timestamp_is_clean(raw_ts, parsed):
                updates.append((parsed, rowid, raw_ts))

        if not dry_run:
            conn.executemany(
                "UPDATE temperature_log SET ts = ? WHERE rowid = ?",
                [(parsed, rowid) for parsed, rowid, _ in updates],
            )

            if delete_bad and bad_rows:
                conn.executemany(
                    "DELETE FROM temperature_log WHERE rowid = ?",
                    [(rowid,) for rowid, _ in bad_rows],
                )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_temperature_log_ts "
                "ON temperature_log(ts)"
            )
            conn.commit()

    print(f"database: {db_path}")
    if backup_path is not None:
        print(f"backup:   {backup_path}")
    print(f"rows checked:       {len(rows)}")
    print(f"timestamps updated: {len(updates)}")
    print(f"unparseable rows:   {len(bad_rows)}")

    if bad_rows and not delete_bad:
        print("")
        print("Unparseable rows were left in place. Re-run with --delete-bad to remove them.")
        for rowid, raw_ts in bad_rows[:10]:
            print(f"  rowid {rowid}: {raw_ts!r}")
        if len(bad_rows) > 10:
            print(f"  ... {len(bad_rows) - 10} more")


def main():
    parser = argparse.ArgumentParser(
        description="Convert temperature_log.ts values to Unix integer seconds."
    )
    parser.add_argument("--db", default=DB_PATH, help=f"database path, default {DB_PATH}")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="inspect the database without changing it",
    )
    parser.add_argument(
        "--delete-bad",
        action="store_true",
        help="delete rows whose timestamps cannot be parsed",
    )
    args = parser.parse_args()
    migrate(args.db, dry_run=args.dry_run, delete_bad=args.delete_bad)


if __name__ == "__main__":
    main()
