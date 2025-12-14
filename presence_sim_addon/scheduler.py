from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import threading

@dataclass
class SchedulerState:
    running: bool = False
    next_run: Optional[str] = None
    last_run: Optional[str] = None

class SimScheduler:
    def __init__(self, on_step: Callable[[datetime], Dict[str, Any]]):
        self._sched = BackgroundScheduler()
        self._lock = threading.Lock()
        self._on_step = on_step
        self.state = SchedulerState()

    def start(self, interval_min: int):
        with self._lock:
            self.stop()
            self._sched.add_job(
                self._job,
                trigger=IntervalTrigger(minutes=int(interval_min)),
                id="presence_sim_step",
                replace_existing=True,
                next_run_time=datetime.now(),
                max_instances=1,
                coalesce=True,
            )
            self._sched.start()
            self.state.running = True
            self._update_next_run()

    def stop(self):
        with self._lock:
            if self._sched.running:
                self._sched.remove_all_jobs()
                self._sched.shutdown(wait=False)
                self._sched = BackgroundScheduler()
            self.state.running = False
            self.state.next_run = None

    def _job(self):
        now = datetime.now().astimezone()
        self.state.last_run = now.isoformat()
        self._on_step(now)
        self._update_next_run()

    def _update_next_run(self):
        job = self._sched.get_job("presence_sim_step")
        self.state.next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
