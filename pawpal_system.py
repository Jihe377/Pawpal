from __future__ import annotations
from dataclasses import dataclass, field
from datetime import time, date
from enum import Enum
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class TaskCategory(Enum):
    WALK = "walk"
    FEEDING = "feeding"
    MEDICATION = "medication"
    ENRICHMENT = "enrichment"
    GROOMING = "grooming"
    VET_VISIT = "vet_visit"
    OTHER = "other"


class Priority(Enum):
    CRITICAL = 4
    HIGH = 3
    MEDIUM = 2
    LOW = 1


class Frequency(Enum):
    ONCE_DAILY = 1
    TWICE_DAILY = 2
    THREE_TIMES_DAILY = 3
    WEEKLY = 7
    AS_NEEDED = 0


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class TimeSlot:
    start: time
    end: time

    @property
    def duration_mins(self) -> int:
        start_mins = self.start.hour * 60 + self.start.minute
        end_mins = self.end.hour * 60 + self.end.minute
        return end_mins - start_mins

    def overlaps(self, other: TimeSlot) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, t: time) -> bool:
        return self.start <= t < self.end

    def to_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


# ---------------------------------------------------------------------------
# Core domain objects
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    constraint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    blocked_slots: list[TimeSlot] = field(default_factory=list)
    max_daily_minutes: int = 480
    max_consecutive_mins: int = 60
    task_exclusions: list[str] = field(default_factory=list)

    def validate(self, scheduled: list[ScheduledTask]) -> bool:
        raise NotImplementedError

    def get_available_slots(self) -> list[TimeSlot]:
        raise NotImplementedError


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    category: TaskCategory = TaskCategory.OTHER
    duration_mins: int = 15
    priority: Priority = Priority.MEDIUM
    frequency: Frequency = Frequency.ONCE_DAILY
    preferred_window: Optional[TimeSlot] = None
    constraint: Optional[Constraint] = None
    is_time_sensitive: bool = False
    notes: str = ""

    def validate(self) -> bool:
        raise NotImplementedError


@dataclass
class Pet:
    pet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    species: str = ""
    breed: str = ""
    age_months: int = 0
    weight_kg: float = 0.0
    tasks: list[Task] = field(default_factory=list)
    constraint: Optional[Constraint] = None

    def add_task(self, task: Task) -> None:
        raise NotImplementedError

    def remove_task(self, task_id: str) -> None:
        raise NotImplementedError

    def get_tasks_by_category(self, cat: TaskCategory) -> list[Task]:
        raise NotImplementedError


@dataclass
class Owner:
    name: str = ""
    available_slots: list[TimeSlot] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)
    timezone: str = "UTC"
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        raise NotImplementedError

    def get_free_time(self) -> list[TimeSlot]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Plan objects
# ---------------------------------------------------------------------------

@dataclass
class ScheduledTask:
    sched_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: Optional[Task] = None
    pet: Optional[Pet] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    priority_score: float = 0.0
    reasoning: str = ""

    def get_duration(self) -> int:
        raise NotImplementedError


@dataclass
class DailyPlan:
    plan_date: Optional[date] = None
    owner: Optional[Owner] = None
    scheduled: list[ScheduledTask] = field(default_factory=list)
    unscheduled: list[Task] = field(default_factory=list)
    overall_reasoning: str = ""
    coverage_pct: float = 0.0

    def get_summary(self) -> str:
        raise NotImplementedError

    def get_timeline(self) -> list:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class Scheduler:
    def schedule(self, owner: Owner, pet: Pet, plan_date: date) -> DailyPlan:
        raise NotImplementedError

    def rank_tasks(self, tasks: list[Task]) -> list[Task]:
        raise NotImplementedError

    def score_slot(self, task: Task, slot: TimeSlot, owner: Owner) -> float:
        raise NotImplementedError

    def find_best_slot(self, task: Task, free_slots: list[TimeSlot]) -> Optional[TimeSlot]:
        raise NotImplementedError

    def explain_decision(self, task: Task) -> str:
        raise NotImplementedError

    def _resolve_conflicts(self, tasks: list[Task]) -> list[Task]:
        raise NotImplementedError

    def _compute_free_slots(self, owner: Owner, plan: DailyPlan) -> list[TimeSlot]:
        raise NotImplementedError
