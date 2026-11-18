from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path.cwd().resolve()
INPUT = ROOT / "Master_Data_Cleaned.xlsx"
DB = ROOT / "data" / "eta.sqlite3"
BACKUPS = ROOT / ".backups"
EXPECTED_DB_SHA256 = "343e1132f35c072fba0109f4e620832ce4c952d09ef0504b8f4d7cc18ca8b79b"
EXPECTED_ROWS = 531
EXPECTED_COUNTS = {"ADD": 530, "UPDATE": 0, "SAME": 1, "MISSING_IN_EXCEL": 0}
EXPECTED_HEADERS = ["Plant", "GSDB", "LLP Person"]
ALLOWED_PLANTS = {"D1D4F", "D1D4H", "D1D4T", "D1D4Y"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def fail(msg: str) -> None:
    print(f"FATAL={msg}")
    print("PRODUCTION_APPLIED=0")
    raise SystemExit(1)


def load_input() -> dict[tuple[str, str], dict]:
    wb = load_workbook(INPUT, read_only=True, data_only=True)
    try:
        if "Data" not in wb.sheetnames:
            fail("SHEET_MISSING:Data")
        ws = wb["Data"]
        headers = [str(ws.cell(1, c).value or "").strip() for c in range(1, 4)]
        if headers != EXPECTED_HEADERS:
            fail(f"HEADER_MISMATCH:{headers!r}")
        result = {}
        for n, values in enumerate(ws.iter_rows(min_row=2, max_col=3, values_only=True), start=2):
            p = str(values[0] or "").strip().upper()
            g = str(values[1] or "").strip().upper()
            o = str(values[2] or "").strip()
            if not p and not g and not o:
                continue
            if p not in ALLOWED_PLANTS:
                fail(f"INVALID_PLANT:ROW_{n}:{p}")
            if len(g) != 5 or not g.isascii() or not g.isalnum():
                fail(f"INVALID_GSDB:ROW_{n}:{g}")
            if not o or len(o) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in o):
                fail(f"INVALID_OWNER:ROW_{n}:{o!r}")
            key = (p, g)
            if key in result:
                fail(f"DUPLICATE_KEY:{p}/{g}:ROWS_{result[key]['excel_row']}_{n}")
            result[key] = {"plant": p, "gsdb": g, "owner": o, "excel_row": n}
        if len(result) != EXPECTED_ROWS:
            fail(f"ROW_COUNT_DRIFT:EXPECTED_{EXPECTED_ROWS}:GOT_{len(result)}")
        return result
    finally:
        wb.close()


def main() -> None:
    if ROOT.name.lower() != "etacontrol":
        fail(f"UNEXPECTED_PROJECT_ROOT:{ROOT}")
    if not INPUT.is_file():
        fail(f"INPUT_MISSING:{INPUT}")
    if not DB.is_file():
        fail(f"DATABASE_MISSING:{DB}")

    before_hash = sha256(DB)
    print(f"DATABASE_SHA256_BEFORE={before_hash}")
    if before_hash != EXPECTED_DB_SHA256:
        fail(f"DATABASE_HASH_DRIFT:{before_hash}")

    incoming = load_input()

    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        current_rows = []
        for plant, gsdb, payload in con.execute("SELECT plant,gsdb,payload FROM suppliers ORDER BY plant,gsdb"):
            obj = json.loads(payload)
            current_rows.append(obj)
    finally:
        con.close()

    current = {(str(r.get('plant') or '').strip().upper(), str(r.get('gsdb') or '').strip().upper()): r for r in current_rows}
    counts = Counter()
    for key, new in incoming.items():
        old = current.get(key)
        if old is None:
            counts["ADD"] += 1
        elif str(old.get("owner") or "").strip() == new["owner"]:
            counts["SAME"] += 1
        else:
            counts["UPDATE"] += 1
    counts["MISSING_IN_EXCEL"] = sum(key not in incoming for key in current)
    actual = {k: counts[k] for k in EXPECTED_COUNTS}
    print("PREVIEW_COUNTS=" + json.dumps(actual, ensure_ascii=False, sort_keys=True))
    if actual != EXPECTED_COUNTS:
        fail(f"PREVIEW_COUNT_DRIFT:{actual!r}")

    # Preserve every existing payload field. New rows follow the active runtime API contract.
    merged = []
    for key, row in sorted(incoming.items()):
        if key in current:
            payload = dict(current[key])
            payload["plant"], payload["gsdb"], payload["owner"] = row["plant"], row["gsdb"], row["owner"]
        else:
            payload = {
                "plant": row["plant"],
                "gsdb": row["gsdb"],
                "owner": row["owner"],
                "tsaa_enabled": True,
                "manual": True,
                "source_refs": ["Master data · Excel"],
            }
        merged.append(payload)

    # Preserve the known baseline record's non-identity fields exactly.
    baseline_key = ("D1D4F", "D05WE")
    if baseline_key not in current or baseline_key not in incoming:
        fail("BASELINE_D05WE_MISSING")
    for k, v in current[baseline_key].items():
        if k not in {"plant", "gsdb", "owner"} and next(x for x in merged if (x["plant"],x["gsdb"])==baseline_key).get(k) != v:
            fail(f"PRESERVATION_FAILURE:D05WE:{k}")

    BACKUPS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUPS / f"MASTER_DATA_EXCEL_V1_PRE_APPLY_{stamp}.sqlite3"
    shutil.copy2(DB, backup)
    if sha256(backup) != before_hash:
        fail("BACKUP_HASH_MISMATCH")
    print(f"BACKUP={backup}")
    print(f"BACKUP_SHA256={sha256(backup)}")

    revision = __import__("uuid").uuid4().hex
    try:
        db = sqlite3.connect(DB, timeout=30)
        try:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM suppliers")
            db.executemany(
                "INSERT INTO suppliers(plant,gsdb,payload) VALUES(?,?,?)",
                [(r["plant"], r["gsdb"], encode(r)) for r in merged],
            )
            db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", ("supplier_revision", encode(revision)))

            # Verify inside the same transaction before commit.
            count = db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
            if count != EXPECTED_ROWS:
                raise RuntimeError(f"POST_WRITE_COUNT:{count}")
            for key, expected in incoming.items():
                raw = db.execute("SELECT payload FROM suppliers WHERE plant=? AND gsdb=?", key).fetchone()
                if not raw:
                    raise RuntimeError(f"POST_WRITE_MISSING:{key[0]}/{key[1]}")
                obj = json.loads(raw[0])
                if obj.get("owner") != expected["owner"]:
                    raise RuntimeError(f"POST_WRITE_OWNER:{key[0]}/{key[1]}")
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as exc:
        # Restore only if the DB changed. The backup is the pre-apply byte-for-byte baseline.
        if DB.exists() and sha256(DB) != before_hash:
            shutil.copy2(backup, DB)
        fail(f"APPLY_FAILED:{type(exc).__name__}:{exc}")

    # Final read-back verification.
    db = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        rows = db.execute("SELECT plant,gsdb,payload FROM suppliers ORDER BY plant,gsdb").fetchall()
        if len(rows) != EXPECTED_ROWS:
            raise RuntimeError(f"FINAL_COUNT:{len(rows)}")
        seen = set()
        for p, g, raw in rows:
            key = (p, g)
            if key in seen:
                raise RuntimeError(f"FINAL_DUPLICATE:{p}/{g}")
            seen.add(key)
            obj = json.loads(raw)
            if obj.get("owner") != incoming[key]["owner"]:
                raise RuntimeError(f"FINAL_OWNER:{p}/{g}")
        rev_row = db.execute("SELECT value FROM meta WHERE key='supplier_revision'").fetchone()
        if not rev_row or json.loads(rev_row[0]) != revision:
            raise RuntimeError("FINAL_REVISION_MISMATCH")
    finally:
        db.close()

    after_hash = sha256(DB)
    print(f"DATABASE_SHA256_AFTER={after_hash}")
    print(f"FINAL_SUPPLIERS={EXPECTED_ROWS}")
    print("FINAL_DUPLICATES=0")
    print("FINAL_BLANK_OWNER=0")
    print("SOURCE_CHANGES=0")
    print("DATABASE_CHANGES=1")
    print("PRODUCTION_APPLIED=1")
    print("GATE=MASTER_DATA_EXCEL_V1_GUARDED_APPLY_PASS")


if __name__ == "__main__":
    main()
