"""Persist and query per-run feature importance without bloating database.py."""

from __future__ import annotations

from database import get_db


def ensure_importance_tables():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feature_importance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            feature TEXT NOT NULL,
            importance REAL NOT NULL,
            rank INTEGER,
            FOREIGN KEY (run_id) REFERENCES model_runs(id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fi_run
        ON feature_importance(run_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fi_feature
        ON feature_importance(feature)
        """
    )
    conn.commit()
    conn.close()


def save_model_run_with_importance(
    model_name,
    version,
    training_rows,
    brier_score,
    log_loss,
    roc_auc,
    notes="",
    feature_importance=None,
):
    """Insert model_runs row + optional feature_importance rows. Returns run_id."""
    ensure_importance_tables()
    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO model_runs (
            model_name, version, trained_at, training_rows,
            brier_score, log_loss, roc_auc, notes
        ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?)
        """,
        (
            model_name,
            version,
            training_rows,
            brier_score,
            log_loss,
            roc_auc,
            notes,
        ),
    )
    run_id = cur.lastrowid

    if feature_importance:
        ranked = sorted(
            feature_importance.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for rank, (feat, imp) in enumerate(ranked, start=1):
            conn.execute(
                """
                INSERT INTO feature_importance (run_id, feature, importance, rank)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, str(feat), float(imp), rank),
            )

    conn.commit()
    conn.close()
    return run_id


def get_feature_importance_history(limit_runs: int = 10):
    ensure_importance_tables()
    conn = get_db()
    rows = conn.execute(
        """
        SELECT fi.run_id, mr.trained_at, mr.version,
               fi.feature, fi.importance, fi.rank
        FROM feature_importance fi
        JOIN model_runs mr ON mr.id = fi.run_id
        WHERE fi.run_id IN (
            SELECT id FROM model_runs
            ORDER BY trained_at DESC
            LIMIT ?
        )
        ORDER BY mr.trained_at DESC, fi.rank ASC
        """,
        (limit_runs,),
    ).fetchall()
    conn.close()
    return rows


def get_model_runs():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM model_runs
        ORDER BY trained_at DESC
        """
    ).fetchall()
    conn.close()
    return rows
