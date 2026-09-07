"""IngestionRun: an operational envelope grouping the ArtifactOccurrences
produced by one collector run.

Deliberately not a transaction boundary: opening one does not hold a
database transaction open for the run's duration, and occurrences within
the run are written independently (see docs/adr/0009-focused-db-spike.md
and the Focused DB Spike Round 1 governance: "Do not make the entire
IngestionRun one transaction").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pg8000.native


@dataclass(frozen=True)
class IngestionRunRecord:
    ingestion_run_id: int


def start_ingestion_run(
    conn: pg8000.native.Connection, *, source: str, started_at: datetime
) -> IngestionRunRecord:
    rows = conn.run(
        "INSERT INTO ingestion_run (source, started_at) VALUES (:source, :started_at) "
        "RETURNING ingestion_run_id",
        source=source,
        started_at=started_at,
    )
    return IngestionRunRecord(ingestion_run_id=rows[0][0])


def finish_ingestion_run(
    conn: pg8000.native.Connection, *, ingestion_run_id: int, finished_at: datetime
) -> None:
    conn.run(
        "UPDATE ingestion_run SET finished_at = :finished_at "
        "WHERE ingestion_run_id = :ingestion_run_id",
        finished_at=finished_at,
        ingestion_run_id=ingestion_run_id,
    )
