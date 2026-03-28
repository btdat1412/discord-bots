import logging
from pathlib import Path

import asyncpg

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Database:
    """Shared async PostgreSQL database with auto-migrations.

    Usage:
        db = Database()
        await db.connect("postgresql://...")
        # All bots share this instance
        row = await db.fetchrow("SELECT * FROM ...", arg1)
        await db.close()
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None

    @property
    def ready(self) -> bool:
        return self._pool is not None

    # ---- Connection ----

    async def connect(self, dsn: str) -> None:
        # Railway may provide postgres:// instead of postgresql://
        dsn = dsn.replace("postgres://", "postgresql://", 1)
        self._pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        await self._run_migrations()
        log.info("Database connected and migrations applied")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    # ---- Query helpers (thin wrappers around pool) ----

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchval(self, query: str, *args):
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    # ---- Migration system ----

    async def _run_migrations(self) -> None:
        """Run all pending SQL migrations in order.

        Migrations are .sql files in the migrations/ directory, named like:
            001_initial.sql
            002_add_images.sql

        A _migrations table tracks which have been applied.
        """
        async with self._pool.acquire() as conn:
            # Create migrations tracking table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Get already-applied migrations
            applied = {
                r["name"]
                for r in await conn.fetch("SELECT name FROM _migrations")
            }

            # Discover and sort migration files
            if not MIGRATIONS_DIR.exists():
                return

            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

            for mf in migration_files:
                if mf.name in applied:
                    continue

                sql = mf.read_text()
                log.info("Applying migration: %s", mf.name)
                try:
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO _migrations (name) VALUES ($1)", mf.name
                    )
                    log.info("Migration applied: %s", mf.name)
                except Exception:
                    log.exception("Migration failed: %s", mf.name)
                    raise
