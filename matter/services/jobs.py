"""Background searches: one thread per run, a slot per session, caps on a shared host (the Studio's model)."""
from __future__ import annotations

import threading
import time

from matter.api.errors import ApiError

MAX_RUNNING = 2                 # concurrent searches on a public host
PUBLIC_JOB_SECONDS = 20 * 60    # a public search is stopped after this long
RETRY_AFTER_S = 30


class Job:
    def __init__(self, run_id: str, session_id: str):
        self.run_id = run_id
        self.session_id = session_id
        self.lock = threading.Lock()
        self.stop_flag = False
        self.started = time.time()
        self.finished: float | None = None
        self.thread: threading.Thread | None = None
        self.max_seconds: int | None = None

    @property
    def running(self) -> bool:
        return self.finished is None


class JobManager:
    def __init__(self, public: bool):
        self.public = public
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def running(self) -> list[Job]:
        return [j for j in self.jobs.values() if j.running]

    def start(self, run_id: str, session_id: str, target, *args, max_seconds: int | None = None) -> Job:
        """Claim a slot and start the thread; 409 when the session already runs a job or the host is full."""
        with self.lock:
            for j in self.running():
                if j.session_id == session_id:
                    raise ApiError("busy", "this session is already running a search; stop it or wait for it to finish", status=409,
                                   retry_after_s=RETRY_AFTER_S)
            if self.public and len(self.running()) >= MAX_RUNNING:
                raise ApiError("busy", f"{MAX_RUNNING} searches are running on this server right now; please try again in a minute",
                               status=409, retry_after_s=RETRY_AFTER_S)
            job = Job(run_id, session_id)
            job.max_seconds = max_seconds
            self.jobs[run_id] = job
        job.thread = threading.Thread(target=self._guard, args=(job, target, args), daemon=True, name=f"search-{run_id}")
        job.thread.start()
        return job

    def _guard(self, job: Job, target, args):
        try:
            target(job, *args)
        finally:
            job.finished = time.time()

    def should_stop(self, job: Job, log=None) -> bool:
        if job.stop_flag:
            return True
        limit = job.max_seconds or PUBLIC_JOB_SECONDS
        if self.public and time.time() - job.started > limit:
            if log:
                log(f"stopped: the limit of {limit // 60} minutes per job on this shared server was reached")
            job.stop_flag = True
            return True
        return False

    def stop(self, run_id: str) -> bool:
        job = self.jobs.get(run_id)
        if job and job.running:
            job.stop_flag = True
            return True
        return False

    def get(self, run_id: str) -> Job | None:
        return self.jobs.get(run_id)
