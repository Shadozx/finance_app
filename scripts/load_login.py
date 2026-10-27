"""Load test for POST /api/v1/auth/login against the app container with a memory limit.

Sends many logins at once and reports the response codes, whether every 503 carries
Retry-After, the response times, the memory peak of the app container and the largest numbers
of open, busy and lock-waiting database connections seen during the run (open ones include
idle connections that wait in the app's pool, busy ones are held by a query or a transaction,
lock-waiting ones are busy ones blocked on a row lock). The logins are spread over --users
users; with one user they queue on the same user row, with as many users as logins they do not.

How to run (the rate limit is switched off for this run only, docker-compose.yml is unchanged):

    docker compose up -d db
    docker compose run --rm --service-ports --name finance_load_app -e RATE_LIMIT_ENABLED=false app
    .venv/Scripts/python.exe scripts/load_login.py --app-container finance_load_app \\
        --db-container finance_tracker_db

If the database is empty, apply the migrations first:

    docker compose run --rm app alembic upgrade head

Use a fresh app container for every run: memory.peak counts from the start of the container,
so a second run in the same container would report the peak of the first one.
"""

import argparse
import asyncio
import statistics
import time
import uuid
from collections import Counter
from typing import NamedTuple

import httpx

# One constant, so a stricter password policy needs a change in one place only
PASSWORD = "LoadTest-Password1"

DEFAULT_APP_URL = "http://localhost:8020"
DEFAULT_CONCURRENCY = 50
# One user means the logins queue on the same row lock; as many users as logins removes it
DEFAULT_USERS = 1
DEFAULT_APP_CONTAINER = "finance_load_app"
DEFAULT_DB_CONTAINER = "finance_tracker_db"
DEFAULT_DB_USER = "finance_user"
DEFAULT_DB_NAME = "finance_tracker"

API_AUTH_REGISTER = "/api/v1/auth/register"
API_AUTH_LOGIN = "/api/v1/auth/login"

# Stands for a login that got no response at all (timeout, refused connection)
NO_RESPONSE = 0

REQUEST_TIMEOUT_SECONDS = 60
DB_POLL_INTERVAL_SECONDS = 0.1
MEMORY_PEAK_PATH = "/sys/fs/cgroup/memory.peak"
BYTES_IN_MIB = 1024 * 1024

# Open connections include idle ones that wait in the app's pool; busy ones are held by a query
# or a transaction; waiting ones are busy ones blocked on a row lock. The query connection
# itself is left out of all three counts.
DB_CONNECTIONS_QUERY = (
    "SELECT count(*), count(*) FILTER (WHERE state <> 'idle'),"
    " count(*) FILTER (WHERE wait_event_type = 'Lock') FROM pg_stat_activity"
    " WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
)
DB_CONNECTIONS_SEPARATOR = "|"


class LoginResult(NamedTuple):
    status_code: int
    has_retry_after: bool
    seconds: float


class DbConnections(NamedTuple):
    open: int
    busy: int
    waiting_for_lock: int


async def docker_exec(container: str, *command: str) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "exec",
        container,
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"docker exec {container} failed: {stderr.decode().strip()}")

    return stdout.decode().strip()


async def register_user(client: httpx.AsyncClient, email: str, username: str) -> None:
    response = await client.post(
        API_AUTH_REGISTER, json={"email": email, "username": username, "password": PASSWORD}
    )

    if response.status_code != httpx.codes.CREATED:
        raise SystemExit(f"Registration failed: {response.status_code} {response.text}")


async def login(client: httpx.AsyncClient, email: str) -> LoginResult:
    started_at = time.perf_counter()

    try:
        response = await client.post(API_AUTH_LOGIN, json={"email": email, "password": PASSWORD})
    except httpx.HTTPError:
        return LoginResult(NO_RESPONSE, False, time.perf_counter() - started_at)

    return LoginResult(
        response.status_code, "Retry-After" in response.headers, time.perf_counter() - started_at
    )


async def watch_db_connections(
    db_container: str, db_user: str, db_name: str, stop: asyncio.Event
) -> DbConnections:
    """Poll the database until stopped and return the largest counts seen, each on its own."""
    query = DB_CONNECTIONS_QUERY.format(db_name=db_name)
    largest = DbConnections(open=0, busy=0, waiting_for_lock=0)

    while not stop.is_set():
        output = await docker_exec(
            db_container, "psql", "-U", db_user, "-d", db_name, "-tAc", query
        )
        current = DbConnections(*(int(value) for value in output.split(DB_CONNECTIONS_SEPARATOR)))
        largest = DbConnections(
            *(max(seen, now) for seen, now in zip(largest, current, strict=True))
        )
        await asyncio.sleep(DB_POLL_INTERVAL_SECONDS)

    return largest


def print_report(
    results: list[LoginResult],
    user_count: int,
    memory_peak_bytes: int,
    max_db_connections: DbConnections,
) -> None:
    status_counts = Counter(result.status_code for result in results)
    unavailable_without_retry_after = sum(
        1
        for result in results
        if result.status_code == httpx.codes.SERVICE_UNAVAILABLE and not result.has_retry_after
    )
    durations = [result.seconds for result in results]

    print(f"Logins sent: {len(results)} by {user_count} user(s)")
    print("Response codes:")
    for status_code, count in sorted(status_counts.items()):
        label = "no response" if status_code == NO_RESPONSE else status_code
        print(f"  {label}: {count}")
    print(f"503 without Retry-After: {unavailable_without_retry_after}")
    print(f"Response time, median: {statistics.median(durations):.2f} s")
    print(f"Response time, worst: {max(durations):.2f} s")
    print(f"Memory peak of the app container: {memory_peak_bytes / BYTES_IN_MIB:.0f} MiB")
    print(f"Most database connections open at once: {max_db_connections.open}")
    print(f"Most database connections busy at once: {max_db_connections.busy}")
    print(
        "Most database connections waiting for a row lock at once: "
        f"{max_db_connections.waiting_for_lock}"
    )


async def run(args: argparse.Namespace) -> None:
    run_id = uuid.uuid4().hex[:8]
    emails = [f"load-{run_id}-{index}@test.com" for index in range(args.users)]
    # The client must hold a connection per login, or requests would wait in the client
    # instead of on the server
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )

    async with httpx.AsyncClient(
        base_url=args.app_url, limits=limits, timeout=REQUEST_TIMEOUT_SECONDS
    ) as client:
        # One by one: registering hashes a password, and many at once would overflow the queue
        for index, email in enumerate(emails):
            await register_user(client, email, f"load_{run_id}_{index}")

        stop_watching = asyncio.Event()
        watcher = asyncio.create_task(
            watch_db_connections(args.db_container, args.db_user, args.db_name, stop_watching)
        )

        try:
            # The logins are spread over the users in turn
            results = await asyncio.gather(
                *(login(client, emails[index % args.users]) for index in range(args.concurrency))
            )
        finally:
            stop_watching.set()

        max_db_connections = await watcher

    memory_peak_bytes = int(await docker_exec(args.app_container, "cat", MEMORY_PEAK_PATH))

    print_report(list(results), args.users, memory_peak_bytes, max_db_connections)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send many logins at once and report the result.")
    parser.add_argument("--app-url", default=DEFAULT_APP_URL)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--users", type=int, default=DEFAULT_USERS)
    parser.add_argument("--app-container", default=DEFAULT_APP_CONTAINER)
    parser.add_argument("--db-container", default=DEFAULT_DB_CONTAINER)
    parser.add_argument("--db-user", default=DEFAULT_DB_USER)
    parser.add_argument("--db-name", default=DEFAULT_DB_NAME)

    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
