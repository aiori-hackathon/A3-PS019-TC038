"""Bounded, read-only ingestion. Sources are read into memory, sampled and released.

Nothing in this module writes source values anywhere. SQLite uploads are opened from
a private temporary file with `mode=ro` and the file is removed as soon as the read
finishes. PostgreSQL connections use a read-only transaction.
"""
from __future__ import annotations

import csv
import io
import os
import random
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_CSV_BYTES = 20 * 1024 * 1024
MAX_SQLITE_BYTES = 50 * 1024 * 1024
MAX_TABLES = 60
MAX_COLUMNS = 400
SAMPLE_SIZES = (500, 1000, 5000)
STRATEGIES = ("head", "random", "stratified")
FETCH_CAP = 60_000
ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
SQLITE_MAGIC = b"SQLite format 3\x00"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Table:
    name: str
    headers: list[str]
    rows: list[list]          # in-memory sample only
    total_rows: int


@dataclass
class SourceRead:
    kind: str
    tables: list[Table]
    notes: list[str] = field(default_factory=list)
    encoding: str | None = None
    delimiter: str | None = None
    read_only_verified: bool = False
    read_only_detail: str = ""
    transient_copy: bool = False
    transient_deleted_at: str | None = None


# ---------------------------------------------------------------- sampling

def sample_rows(rows: list[list], size: int, strategy: str, seed: int = 7) -> list[list]:
    if len(rows) <= size:
        return list(rows)
    rng = random.Random(seed)
    if strategy == "head":
        return rows[:size]
    if strategy == "random":
        return rng.sample(rows, size)
    # stratified: ten equal position bands, equal draws from each
    bands = 10
    per = size // bands
    out: list[list] = []
    step = len(rows) / bands
    for b in range(bands):
        chunk = rows[int(b * step):int((b + 1) * step)]
        out.extend(rng.sample(chunk, min(per, len(chunk))))
    return out


def check_options(size: int, strategy: str) -> None:
    if size not in SAMPLE_SIZES:
        raise ValueError(f"Sample size must be one of {', '.join(map(str, SAMPLE_SIZES))}")
    if strategy not in STRATEGIES:
        raise ValueError(f"Sampling strategy must be one of {', '.join(STRATEGIES)}")


# ---------------------------------------------------------------- headers

def dedupe_headers(headers: list[str]) -> tuple[list[str], list[str]]:
    seen: dict[str, int] = {}
    out, notes = [], []
    for i, h in enumerate(headers):
        name = (h or "").strip()[:120] or f"column_{i + 1}"
        if name in seen:
            seen[name] += 1
            new = f"{name}_{seen[name]}"
            notes.append(f"Duplicate header '{name}' renamed to '{new}'")
            name = new
        else:
            seen[name] = 1
        out.append(name)
    return out, notes


# ---------------------------------------------------------------- CSV

def decode(data: bytes) -> tuple[str, str]:
    for enc in ENCODINGS:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode file")  # pragma: no cover - latin-1 always decodes


def sniff_delimiter(text: str) -> str:
    """Pick the delimiter that appears consistently on the first lines; fall back to csv.Sniffer."""
    lines = [l for l in text[:65536].splitlines()[:30] if l.strip()]
    best, best_score = None, 0
    for d in (",", ";", "\t", "|"):
        counts = [l.count(d) for l in lines]
        if counts and counts[0] > 0:
            consistent = sum(1 for c in counts if c >= 1) / len(counts)
            score = counts[0] * consistent
            if consistent >= 0.6 and score > best_score:
                best, best_score = d, score
    if best:
        return best
    try:
        return csv.Sniffer().sniff(text[:65536], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def read_csv(data: bytes, name: str, size: int, strategy: str) -> SourceRead:
    if len(data) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds the 20 MB limit")
    if not data.strip():
        raise ValueError("The CSV file is empty")
    if data.startswith(SQLITE_MAGIC):
        raise ValueError("This looks like a SQLite database, not a CSV")
    text, encoding = decode(data)
    delimiter = sniff_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise ValueError("The CSV file has no header row") from None
    if len(raw_headers) > MAX_COLUMNS:
        raise ValueError(f"CSV has more than {MAX_COLUMNS} columns")
    headers, notes = dedupe_headers(raw_headers)
    width = len(headers)
    rows, ragged = [], 0
    try:
        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            if len(row) != width:
                ragged += 1
                row = (row + [""] * width)[:width]
            rows.append(row)
    except csv.Error as exc:
        raise ValueError(f"CSV could not be parsed: {exc}") from exc
    if ragged:
        notes.append(f"{ragged} rows had a different number of fields and were padded or trimmed")
    if encoding not in ("utf-8-sig", "utf-8"):
        notes.append(f"File was not valid UTF-8; decoded as {encoding}")
    total = len(rows)
    sample = sample_rows(rows, size, strategy)
    del rows
    table = Path(name).stem or "csv"
    return SourceRead("CSV", [Table(table, headers, sample, total)], notes, encoding, delimiter,
                      read_only_verified=True, read_only_detail="CSV is parsed in memory; there is nothing to write back to.")


# ---------------------------------------------------------------- SQLite

def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sqlite_readonly_selftest(conn: sqlite3.Connection) -> tuple[bool, str]:
    try:
        conn.execute("BEGIN")
        conn.execute("CREATE TABLE __privacytwin_probe(x)")
    except sqlite3.OperationalError as exc:
        conn.rollback()
        return True, f"Write attempt refused by SQLite ({exc}); connection is read-only."
    conn.rollback()
    return False, "A test write was not refused. The scan was stopped."


def _sqlite_tables(conn, size, strategy) -> list[Table]:
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    if not names:
        raise ValueError("The SQLite database has no tables")
    if len(names) > MAX_TABLES:
        raise ValueError(f"SQLite has more than {MAX_TABLES} tables")
    tables = []
    for name in names:
        q = quote_ident(name)
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM {q}").fetchone()[0]
        except sqlite3.DatabaseError:
            continue  # virtual tables needing missing modules
        order = "ORDER BY RANDOM()" if strategy == "random" and total > size else ""
        limit = size if strategy == "head" else FETCH_CAP
        cur = conn.execute(f"SELECT * FROM {q} {order} LIMIT ?", (limit,))
        raw_headers = [d[0] for d in cur.description]
        if len(raw_headers) > MAX_COLUMNS:
            raise ValueError(f"Table {name} has more than {MAX_COLUMNS} columns")
        headers, _ = dedupe_headers(raw_headers)
        rows = [["" if isinstance(v, (bytes, memoryview)) else v for v in row] for row in cur]
        tables.append(Table(name, headers, sample_rows(rows, size, strategy if strategy != "random" else "head"), total))
    return tables


def read_sqlite_bytes(data: bytes, size: int, strategy: str) -> SourceRead:
    if len(data) > MAX_SQLITE_BYTES:
        raise ValueError("SQLite file exceeds the 50 MB limit")
    if not data.startswith(SQLITE_MAGIC):
        raise ValueError("This file is not a SQLite database")
    fd, path = tempfile.mkstemp(prefix="pt-", suffix=".sqlite")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        result = read_sqlite_path(Path(path), size, strategy)
        result.transient_copy = True
        return result
    finally:
        try:
            os.remove(path)
        except OSError:  # pragma: no cover
            pass


def read_sqlite_path(path: Path, size: int, strategy: str) -> SourceRead:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, isolation_level=None)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            ok, detail = sqlite_readonly_selftest(conn)
            if not ok:
                raise ValueError(detail)
            tables = _sqlite_tables(conn, size, strategy)
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Could not read SQLite database: {exc}") from exc
    return SourceRead("SQLite", tables, read_only_verified=True, read_only_detail=detail,
                      transient_deleted_at=now_iso())


def read_memory_tables(tables: dict[str, tuple[list[str], list[list]]], size: int, strategy: str) -> SourceRead:
    """Used by the synthetic demo: tables generated in memory."""
    out = []
    for name, (headers, rows) in tables.items():
        out.append(Table(name, headers, sample_rows(rows, size, strategy), len(rows)))
    return SourceRead("SQLite", out, read_only_verified=True,
                      read_only_detail="Synthetic tables generated in memory; nothing to write back to.")


# ---------------------------------------------------------------- PostgreSQL

def read_postgres(dsn: str, size: int, strategy: str) -> SourceRead:  # pragma: no cover - needs a server
    try:
        import psycopg  # type: ignore
        from psycopg import sql  # type: ignore
    except ImportError as exc:
        raise ValueError("PostgreSQL support needs the optional 'psycopg[binary]' package") from exc
    if len(dsn) > 1000:
        raise ValueError("Connection string is too long")
    with psycopg.connect(dsn, connect_timeout=8, options="-c statement_timeout=15000") as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE TEMP TABLE __privacytwin_probe(x int)")
                conn.rollback()
                raise ValueError("A test write was not refused. Use a read-only user.")
            except psycopg.errors.ReadOnlySqlTransaction as exc:
                conn.rollback()
                detail = f"Write attempt refused ({exc.diag.message_primary}); transaction is read-only."
            cur.execute("""SELECT table_schema, table_name FROM information_schema.tables
                           WHERE table_type='BASE TABLE' AND table_schema NOT IN ('pg_catalog','information_schema')
                           ORDER BY 1,2 LIMIT %s""", (MAX_TABLES,))
            names = cur.fetchall()
            writable = []
            tables = []
            for schema, name in names:
                ident = sql.Identifier(schema, name)
                cur.execute(sql.SQL("SELECT has_table_privilege(current_user, {}, 'INSERT')").format(
                    sql.Literal(f'"{schema}"."{name}"')))
                if cur.fetchone()[0]:
                    writable.append(f"{schema}.{name}")
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(ident))
                total = cur.fetchone()[0]
                order = sql.SQL("ORDER BY random()") if strategy == "random" else sql.SQL("")
                cur.execute(sql.SQL("SELECT * FROM {} {} LIMIT {}").format(ident, order, sql.Literal(FETCH_CAP if strategy == "stratified" else size)))
                headers, _ = dedupe_headers([d.name for d in cur.description])
                rows = [list(r) for r in cur.fetchall()]
                label = name if schema == "public" else f"{schema}.{name}"
                tables.append(Table(label, headers, sample_rows(rows, size, "head" if strategy == "random" else strategy), total))
            conn.rollback()
    notes = []
    if writable:
        notes.append(f"The database user can write to {len(writable)} tables. PrivacyTwin did not write, "
                     "but a dedicated read-only role is recommended.")
    return SourceRead("PostgreSQL", tables, notes, read_only_verified=True, read_only_detail=detail)


def detect_kind(filename: str, data: bytes) -> str:
    if data.startswith(SQLITE_MAGIC):
        return "SQLite"
    ext = Path(filename).suffix.lower()
    if ext in (".db", ".sqlite", ".sqlite3"):
        raise ValueError("The file has a SQLite extension but is not a SQLite database")
    if ext in (".csv", ".txt", ".tsv", ""):
        return "CSV"
    raise ValueError(f"Unsupported file type '{ext}'. Upload a CSV or SQLite file.")
