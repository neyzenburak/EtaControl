from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path.cwd().resolve()
INPUT = ROOT / "Master_Data_Cleaned.xlsx"
DB = ROOT / "data" / "eta.sqlite3"
BACKUPS = ROOT / ".backups"
SHEET = "Data"
EXPECTED_HEADERS = ["Plant", "GSDB", "LLP Person"]
EXPECTED_ROWS = 531
ALLOWED_PLANTS = {"D1D4F", "D1D4H", "D1D4T", "D1D4Y"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def fail(message: str, backup: Path | None = None) -> None:
    print(f"FATAL={message}")
    if backup:
        print(f"BACKUP={backup}")
    print("PRODUCTION_APPLIED=0")
    raise SystemExit(1)


def load_input() -> dict[tuple[str, str], dict]:
    try:
        wb = load_workbook(INPUT, read_only=True, data_only=True)
    except Exception as exc:
        fail(f"WORKBOOK_OPEN_FAILED:{type(exc).__name__}:{exc}")
    try:
        if SHEET not in wb.sheetnames:
            fail(f"SHEET_MISSING:{SHEET}")
        ws = wb[SHEET]
        headers = [str(ws.cell(1, c).value or "").strip() for c in range(1, 4)]
        if headers != EXPECTED_HEADERS:
            fail(f"HEADER_MISMATCH:{headers!r}")

        incoming: dict[tuple[str, str], dict] = {}
        plant_counts = Counter()
        for row_no, values in enumerate(ws.iter_rows(min_row=2, max_col=3, values_only=True), start=2):
            plant = str(values[0] or "").strip().upper()
            gsdb = str(values[1] or "").strip().upper()
            owner = str(values[2] or "").strip()
            if not plant and not gsdb and not owner:
                continue
            if plant not in ALLOWED_PLANTS:
                fail(f"INVALID_PLANT:ROW_{row_no}:{plant}")
            if len(gsdb) != 5 or not gsdb.isascii() or not gsdb.isalnum():
                fail(f"INVALID_GSDB:ROW_{row_no}:{gsdb}")
            if not owner or len(owner) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in owner):
                fail(f"INVALID_OWNER:ROW_{row_no}:{owner!r}")
            key = (plant, gsdb)
            if key in incoming:
                fail(f"DUPLICATE_KEY:{plant}/{gsdb}:ROWS_{incoming[key]['excel_row']}_{row_no}")
            incoming[key] = {"plant": plant, "gsdb": gsdb, "owner": owner, "excel_row": row_no}
            plant_counts[plant] += 1

        if len(incoming) != EXPECTED_ROWS:
            fail(f"ROW_COUNT_DRIFT:EXPECTED_{EXPECTED_ROWS}:GOT_{len(incoming)}")
        print("PLANT_COUNTS=" + json.dumps(dict(sorted(plant_counts.items())), ensure_ascii=False))
        return incoming
    finally:
        wb.close()


def read_state(read_only: bool = True) -> tuple[dict[tuple[str, str], dict], dict]:
    uri = f"file:{DB.as_posix()}?mode={'ro' if read_only else 'rw'}"
    db = sqlite3.connect(uri, uri=True, timeout=30)
    try:
        table_names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"meta", "suppliers", "runs", "shipments"}
        if not required <= table_names:
            fail(f"DATABASE_SCHEMA_MISSING:{sorted(required-table_names)}")
        suppliers = {}
        for plant, gsdb, raw in db.execute("SELECT plant,gsdb,payload FROM suppliers ORDER BY plant,gsdb"):
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                fail(f"NON_OBJECT_PAYLOAD:{plant}/{gsdb}")
            key = (str(plant).strip().upper(), str(gsdb).strip().upper())
            if key in suppliers:
                fail(f"DATABASE_DUPLICATE:{key[0]}/{key[1]}")
            suppliers[key] = payload
        meta = {k: json.loads(v) for k, v in db.execute("SELECT key,value FROM meta")}
        return suppliers, meta
    finally:
        db.close()


def main() -> None:
    if ROOT.name.lower() != "etacontrol":
        fail(f"UNEXPECTED_PROJECT_ROOT:{ROOT}")
    if not INPUT.is_file():
        fail(f"INPUT_MISSING:{INPUT}")
    if not DB.is_file():
        fail(f"DATABASE_MISSING:{DB}")

    input_hash = sha256(INPUT)
    before_hash = sha256(DB)
    print(f"INPUT_SHA256={input_hash}")
    print(f"DATABASE_SHA256_BEFORE={before_hash}")

    incoming = load_input()
    current, meta = read_state()

    counts = Counter()
    for key, row in incoming.items():
        old = current.get(key)
        if old is None:
            counts["ADD"] += 1
        elif str(old.get("owner") or "").strip() == row["owner"]:
            counts["SAME"] += 1
        else:
            counts["UPDATE"] += 1
    counts["MISSING_IN_EXCEL"] = sum(key not in incoming for key in current)
    preview = {k: counts[k] for k in ("ADD", "UPDATE", "SAME", "MISSING_IN_EXCEL")}
    print("PREVIEW_COUNTS=" + json.dumps(preview, ensure_ascii=False, sort_keys=True))

    # Portable replace contract: workbook is authoritative for the supplier key set.
    # Existing payload fields survive for matching identities. Existing identities absent
    # from Excel are intentionally removed and reported before apply.
    merged = []
    for key, row in sorted(incoming.items()):
        old = current.get(key)
        if old is None:
            payload = {
                "plant": row["plant"],
                "gsdb": row["gsdb"],
                "owner": row["owner"],
                "tsaa_enabled": True,
                "manual": True,
                "source_refs": ["Master data · Excel portable V1"],
            }
        else:
            payload = dict(old)
            payload.update(plant=row["plant"], gsdb=row["gsdb"], owner=row["owner"])
        merged.append(payload)

    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUPS / f"MASTER_DATA_EXCEL_PORTABLE_V1_PRE_APPLY_{stamp}.sqlite3"
    shutil.copy2(DB, backup)
    backup_hash = sha256(backup)
    if backup_hash != before_hash:
        fail("BACKUP_HASH_MISMATCH", backup)
    print(f"BACKUP={backup}")
    print(f"BACKUP_SHA256={backup_hash}")

    revision = uuid.uuid4().hex
    try:
        db = sqlite3.connect(DB, timeout=30)
        try:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")

            # Revalidate state inside transaction to catch concurrent changes.
            live_count = db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
            if live_count != len(current):
                raise RuntimeError(f"CONCURRENT_SUPPLIER_CHANGE:EXPECTED_{len(current)}:GOT_{live_count}")

            db.execute("DELETE FROM suppliers")
            db.executemany(
                "INSERT INTO suppliers(plant,gsdb,payload) VALUES(?,?,?)",
                [(r["plant"], r["gsdb"], encode(r)) for r in merged],
            )

            # Propagate owner changes into all historical run records, preserving raw fields.
            owners = {(r["plant"], r["gsdb"]): r["owner"] for r in merged}
            run_rows = db.execute("SELECT id,payload FROM runs").fetchall()
            for run_row in run_rows:
                run = json.loads(run_row["payload"])
                records = []
                shipment_rows = db.execute(
                    "SELECT payload FROM shipments WHERE run_id=? ORDER BY plant,asn,id", (run_row["id"],)
                ).fetchall()
                for shipment_row in shipment_rows:
                    record = json.loads(shipment_row["payload"])
                    key = (str(record.get("plant") or "").strip().upper(), str(record.get("supplier") or "").strip().upper())
                    if key in owners:
                        record["owner"] = owners[key]
                        issues = [i for i in record.get("issues", []) if i not in {"MISSING_OWNER", "OWNER_REPAIRED"}]
                        if not record["owner"]:
                            issues.append("MISSING_OWNER")
                        elif str(record.get("source_owner") or "") != record["owner"]:
                            issues.append("OWNER_REPAIRED")
                        record["issues"] = issues
                    records.append(record)

                stats = run.setdefault("stats", {})
                stats["owner_coverage"] = sum(bool(r.get("owner")) for r in records)
                stats["owners_repaired"] = sum("OWNER_REPAIRED" in r.get("issues", []) for r in records)
                stats["issues"] = dict(Counter(i for r in records for i in r.get("issues", [])))
                run["mapping_revision"] = revision
                db.execute(
                    "UPDATE runs SET payload=? WHERE id=?", (encode(run), run_row["id"])
                )
                db.execute("DELETE FROM shipments WHERE run_id=?", (run_row["id"],))
                db.executemany(
                    "INSERT INTO shipments(run_id,id,plant,asn,supplier,payload) VALUES(?,?,?,?,?,?)",
                    [
                        (
                            run_row["id"], r["id"], r.get("plant"), r.get("asn"),
                            r.get("supplier"), encode(r),
                        )
                        for r in records
                    ],
                )

            db.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)",
                ("supplier_revision", encode(revision)),
            )

            # Verify within the same transaction.
            if db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] != EXPECTED_ROWS:
                raise RuntimeError("POST_WRITE_COUNT_MISMATCH")
            for key, row in incoming.items():
                found = db.execute("SELECT payload FROM suppliers WHERE plant=? AND gsdb=?", key).fetchone()
                if not found or json.loads(found[0]).get("owner") != row["owner"]:
                    raise RuntimeError(f"POST_WRITE_MISMATCH:{key[0]}/{key[1]}")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as exc:
        if DB.exists() and sha256(DB) != before_hash:
            shutil.copy2(backup, DB)
        fail(f"APPLY_FAILED:{type(exc).__name__}:{exc}", backup)

    try:
        final, final_meta = read_state()
        if len(final) != EXPECTED_ROWS:
            raise RuntimeError(f"FINAL_COUNT:{len(final)}")
        if set(final) != set(incoming):
            raise RuntimeError("FINAL_KEYSET_MISMATCH")
        if any(str(final[k].get("owner") or "").strip() != incoming[k]["owner"] for k in incoming):
            raise RuntimeError("FINAL_OWNER_MISMATCH")
        if final_meta.get("supplier_revision") != revision:
            raise RuntimeError("FINAL_REVISION_MISMATCH")
    except Exception as exc:
        shutil.copy2(backup, DB)
        fail(f"FINAL_VALIDATION_FAILED:{type(exc).__name__}:{exc}", backup)

    after_hash = sha256(DB)
    print(f"DATABASE_SHA256_AFTER={after_hash}")
    print(f"FINAL_SUPPLIERS={len(final)}")
    print("FINAL_DUPLICATES=0")
    print("FINAL_BLANK_OWNER=0")
    print("SOURCE_CHANGES=0")
    print("DATABASE_CHANGES=1")
    print("PRODUCTION_APPLIED=1")
    print("GATE=MASTER_DATA_EXCEL_PORTABLE_V1_GUARDED_APPLY_PASS")


if __name__ == "__main__":
    main()
