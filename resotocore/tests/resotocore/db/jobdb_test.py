import asyncio
import pytest
from arango.database import StandardDatabase
from datetime import timedelta
from typing import List

from resotocore.analytics import InMemoryEventSender
from resotocore.db import jobdb
from resotocore.db.async_arangodb import AsyncArangoDB
from resotocore.db.entitydb import EventEntityDb
from resotocore.db.jobdb import JobDb, EventJobDb
from resotocore.task.task_description import Job, ExecuteCommand, EventTrigger
from resotocore.ids import TaskDescriptorId

# noinspection PyUnresolvedReferences
from tests.resotocore.analytics import event_sender

# noinspection PyUnresolvedReferences
from tests.resotocore.db.graphdb_test import test_db, local_client, system_db


@pytest.fixture
async def job_db(test_db: StandardDatabase) -> JobDb:
    async_db = AsyncArangoDB(test_db)
    job_db = jobdb.job_db(async_db, "jobs")
    await job_db.create_update_schema()
    await job_db.wipe()
    return job_db


@pytest.fixture
def event_db(job_db: JobDb, event_sender: InMemoryEventSender) -> EventJobDb:
    return EventEntityDb(job_db, event_sender, "job")


@pytest.fixture
def jobs() -> List[Job]:
    wait = (EventTrigger("wait"), timedelta(seconds=30))
    return [
        Job(TaskDescriptorId("id1"), ExecuteCommand("echo hello"), timedelta(seconds=10), EventTrigger("run_job")),
        Job(TaskDescriptorId("id2"), ExecuteCommand("sleep 10"), timedelta(seconds=10), EventTrigger("run_job"), wait),
    ]


def job_id(job: Job) -> str:
    return job.id


@pytest.mark.asyncio
async def test_load(job_db: JobDb, jobs: List[Job]) -> None:
    await job_db.update_many(jobs)
    loaded = [sub async for sub in job_db.all()]
    assert jobs.sort(key=job_id) == loaded.sort(key=job_id)


@pytest.mark.asyncio
async def test_update(job_db: JobDb, jobs: List[Job]) -> None:
    # multiple updates should work as expected
    await job_db.update_many(jobs)
    await job_db.update_many(jobs)
    await job_db.update_many(jobs)
    loaded = [sub async for sub in job_db.all()]
    assert jobs.sort(key=job_id) == loaded.sort(key=job_id)


@pytest.mark.asyncio
async def test_delete(job_db: JobDb, jobs: List[Job]) -> None:
    await job_db.update_many(jobs)
    remaining = list(jobs)
    for _ in jobs:
        sub = remaining.pop()
        await job_db.delete_value(sub)
        loaded = [sub async for sub in job_db.all()]
        assert remaining.sort(key=job_id) == loaded.sort(key=job_id)
    assert len([sub async for sub in job_db.all()]) == 0


@pytest.mark.asyncio
async def test_events(event_db: EventJobDb, jobs: List[Job], event_sender: InMemoryEventSender) -> None:
    # 2 times update
    await event_db.update_many(jobs)
    await event_db.update_many(jobs)
    # 2 times delete
    for sub in jobs:
        await event_db.delete_value(sub)
    # make sure all events will arrive
    await asyncio.sleep(0.1)
    # ensure the correct count and order of events
    assert [a.kind for a in event_sender.events] == ["job-updated-many"] * 2 + ["job-deleted"] * 2
