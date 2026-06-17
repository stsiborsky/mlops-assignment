"""Schema-rendering helper (provided complete).

Loads the schema directly from sqlite and renders quoted CREATE TABLE
text suitable for prompt context. Identifiers are always double-quoted
so reserved-word table/column names (e.g. `order`) don't break either
the PRAGMA introspection here or the SQL the model emits later.

Column descriptions from BIRD's `database_description/<table>.csv` files
are merged in as trailing `-- ...` comments. The CSVs include
human-readable column names, descriptions, and "Commonsense evidence"
hints (e.g. "Normal range: 900 < N < 2000") that the model needs to
answer questions involving domain ranges or value mappings.
"""
from __future__ import annotations

import csv
import logging
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data" / "bird"
DESC_DIR = DB_DIR / "dev_20240627" / "dev_databases"

logger = logging.getLogger(__name__)


def db_path(db_id: str) -> Path:
    return DB_DIR / f"{db_id}.sqlite"


def _q(ident: str) -> str:
    """Double-quote a SQL identifier, escaping any embedded quotes."""
    return '"' + ident.replace('"', '""') + '"'


def _flatten(text: str) -> str:
    """Collapse whitespace so a multi-line CSV cell fits on one schema line."""
    return re.sub(r"\s+", " ", text).strip()


def _read_table_descriptions(db_id: str, table: str) -> dict[str, str]:
    """Return {column_name -> one-line description} from BIRD's CSVs.

    BIRD ships `database_description/<table>.csv` per DB with columns:
    original_column_name, column_name, column_description, data_format,
    value_description. We merge name/description/value_description into a
    single line. Lookup is case-insensitive because some CSVs disagree
    with the SQLite catalog on casing.
    """
    csv_path = DESC_DIR / db_id / "database_description" / f"{table}.csv"
    if not csv_path.exists():
        return {}
    out: dict[str, str] = {}
    # BIRD CSVs are mostly utf-8 but a few have stray bytes; fall back to latin-1.
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with csv_path.open(encoding=encoding, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    col = (row.get("original_column_name") or "").strip()
                    if not col:
                        continue
                    pretty = _flatten(row.get("column_name") or "")
                    desc = _flatten(row.get("column_description") or "")
                    vdesc = _flatten(row.get("value_description") or "")
                    parts = []
                    if pretty and pretty.lower() != col.lower():
                        parts.append(pretty)
                    if desc and desc.lower() != pretty.lower():
                        parts.append(desc)
                    if vdesc:
                        parts.append(vdesc)
                    text = "; ".join(parts)
                    if text:
                        out[col.lower()] = text
            return out
        except UnicodeDecodeError:
            logger.exception("decode failed for %s with encoding=%s", csv_path, encoding)
            continue
    return out


@lru_cache(maxsize=32)
def render_schema(db_id: str) -> str:
    path = db_path(db_id)
    if not path.exists():
        raise FileNotFoundError(f"DB {db_id} not found at {path}. Did you run scripts/load_data.py?")

    parts: list[str] = [f"-- Database: {db_id}"]
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
        ]
        for t in tables:
            descs = _read_table_descriptions(db_id, t)
            parts.append(f"\nCREATE TABLE {_q(t)} (")
            # Each entry is (code, comment_or_empty); comma is attached during render
            # so it goes BEFORE the comment, not inside it.
            entries: list[tuple[str, str]] = []
            for _cid, name, ctype, notnull, _dflt, pk in conn.execute(f"PRAGMA table_info({_q(t)})"):
                code = f"  {_q(name)} {ctype}"
                if pk:
                    code += " PRIMARY KEY"
                if notnull and not pk:
                    code += " NOT NULL"
                entries.append((code, descs.get(name.lower(), "")))
            for fk in conn.execute(f"PRAGMA foreign_key_list({_q(t)})"):
                # (id, seq, ref_table, from, to, on_update, on_delete, match)
                entries.append((
                    f"  FOREIGN KEY ({_q(fk[3])}) REFERENCES {_q(fk[2])}({_q(fk[4])})",
                    "",
                ))
            rendered = []
            for i, (code, comment) in enumerate(entries):
                sep = "," if i < len(entries) - 1 else ""
                if comment:
                    rendered.append(f"{code}{sep}  -- {comment}")
                else:
                    rendered.append(f"{code}{sep}")
            parts.append("\n".join(rendered))
            parts.append(");")
    return "\n".join(parts)


def available_dbs() -> list[str]:
    if not DB_DIR.exists():
        return []
    return sorted(p.stem for p in DB_DIR.glob("*.sqlite"))
