from __future__ import annotations
from dataclasses import dataclass, field
from datetime import time, date, timedelta
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
# Module-level helpers
# ---------------------------------------------------------------------------

def _time_to_mins(t: time) -> int:
    return t.hour * 60 + t.minute


def _mins_to_time(m: int) -> time:
    return time(m // 60, m % 60)


def _trim_slots_before(slots: list[TimeSlot], earliest_mins: int) -> list[TimeSlot]:
    """Drop or trim slots so none start before earliest_mins."""
    result = []
    for s in slots:
        s_end = _time_to_mins(s.end)
        if s_end <= earliest_mins:
            continue
        s_start = _time_to_mins(s.start)
        if s_start < earliest_mins:
            result.append(TimeSlot(_mins_to_time(earliest_mins), s.end))
        else:
            result.append(s)
    return result


def _subtract_booked(slots: list[TimeSlot], booked: TimeSlot) -> list[TimeSlot]:
    """Remove a booked period from a list of free slots, splitting where needed."""
    result = []
    for slot in slots:
        if not slot.overlaps(booked):
            result.append(slot)
        else:
            if slot.start < booked.start:
                result.append(TimeSlot(slot.start, booked.start))
            if booked.end < slot.end:
                result.append(TimeSlot(booked.end, slot.end))
    return result


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class TimeSlot:
    start: time
    end: time

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError(
                f"TimeSlot start ({self.start}) must be before end ({self.end})"
            )

    @property
    def duration_mins(self) -> int:
        return _time_to_mins(self.end) - _time_to_mins(self.start)

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
        """Return False if scheduled tasks violate budget, blocked slots, or exclusions."""
        total_mins = sum(st.get_duration() for st in scheduled)
        if total_mins > self.max_daily_minutes:
            return False
        for st in scheduled:
            if st.task and st.task.task_id in self.task_exclusions:
                return False
            if st.start_time and st.end_time:
                booked = TimeSlot(st.start_time, st.end_time)
                if any(booked.overlaps(b) for b in self.blocked_slots):
                    return False
        return True

    def get_available_slots(self, already_scheduled: list[ScheduledTask]) -> list[TimeSlot]:
        """Full day minus blocked_slots minus already-occupied time."""
        free: list[TimeSlot] = [TimeSlot(time(0, 0), time(23, 59))]
        for blocked in self.blocked_slots:
            free = _subtract_booked(free, blocked)
        for st in already_scheduled:
            if st.start_time and st.end_time:
                free = _subtract_booked(free, TimeSlot(st.start_time, st.end_time))
        return free


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    category: TaskCategory = TaskCategory.OTHER
    duration_mins: int = 15
    priority: Priority = Priority.MEDIUM
    frequency: Frequency = Frequency.ONCE_DAILY
    preferred_window: Optional[TimeSlot] = None
    is_time_sensitive: bool = False
    is_completed: bool = False
    notes: str = ""
    due_date: Optional[date] = None

    # How many days until the next occurrence for each frequency.
    # timedelta(days=n) shifts a date forward by exactly n days,
    # correctly handling month boundaries and leap years.
    _RECURRENCE_DAYS: dict = field(default_factory=lambda: {
        Frequency.ONCE_DAILY:        timedelta(days=1),
        Frequency.TWICE_DAILY:       timedelta(days=1),
        Frequency.THREE_TIMES_DAILY: timedelta(days=1),
        Frequency.WEEKLY:            timedelta(weeks=1),  # timedelta(weeks=1) == timedelta(days=7)
    })

    def mark_complete(self) -> Optional[Task]:
        """Mark this task done and return a fresh Task for the next occurrence.

        Returns:
            A new Task with a reset is_completed and an updated due_date,
            or None if the frequency is AS_NEEDED (no automatic recurrence).
        """
        self.is_completed = True

        delta = self._RECURRENCE_DAYS.get(self.frequency)
        if delta is None:           # AS_NEEDED — caller decides if/when to reschedule
            return None

        # date.today() + timedelta gives the concrete calendar date of the next run.
        # Example: today=2026-03-29, daily  → 2026-03-30
        #          today=2026-03-29, weekly → 2026-04-05
        next_due = (self.due_date or date.today()) + delta

        return Task(
            name=self.name,
            category=self.category,
            duration_mins=self.duration_mins,
            priority=self.priority,
            frequency=self.frequency,
            preferred_window=self.preferred_window,
            is_time_sensitive=self.is_time_sensitive,
            notes=self.notes,
            due_date=next_due,
        )

    def validate(self) -> bool:
        """Return True if the task is internally consistent."""
        if not self.name.strip():
            return False
        if self.duration_mins <= 0:
            return False
        if self.preferred_window is not None:
            if self.preferred_window.duration_mins < self.duration_mins:
                return False
        return True


@dataclass
class Pet:
    pet_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    species: str = ""
    breed: str = ""
    age_months: int = 0
    weight_kg: float = 0.0
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> None:
        self.tasks = [t for t in self.tasks if t.task_id != task_id]

    def get_tasks_by_category(self, cat: TaskCategory) -> list[Task]:
        return [t for t in self.tasks if t.category == cat]


@dataclass
class Owner:
    name: str = ""
    available_slots: list[TimeSlot] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)
    timezone: str = "UTC"
    pets: list[Pet] = field(default_factory=list)

    def add_pet(self, pet: Pet) -> None:
        self.pets.append(pet)

    def remove_pet(self, pet_id: str) -> None:
        self.pets = [p for p in self.pets if p.pet_id != pet_id]

    def filter_tasks(
        self,
        *,
        is_completed: Optional[bool] = None,
        pet_name: Optional[str] = None,
    ) -> list[Task]:
        """Return tasks across all pets, optionally filtered by completion status or pet name.

        Args:
            is_completed: if True, return only completed tasks; if False, only incomplete.
                          if None, completion status is not filtered.
            pet_name:     if given, return only tasks belonging to that pet (case-insensitive).
                          if None, tasks from all pets are included.
        """
        results: list[Task] = []
        for pet in self.pets:
            if pet_name is not None and pet.name.lower() != pet_name.lower():
                continue
            for task in pet.tasks:
                if is_completed is not None and task.is_completed != is_completed:
                    continue
                results.append(task)
        return results

    def get_free_time(self, already_scheduled: list[ScheduledTask]) -> list[TimeSlot]:
        """Owner's available_slots minus time already occupied by scheduled tasks."""
        free = list(self.available_slots)
        for st in already_scheduled:
            if st.start_time and st.end_time:
                free = _subtract_booked(free, TimeSlot(st.start_time, st.end_time))
        return free


# ---------------------------------------------------------------------------
# Plan objects
# ---------------------------------------------------------------------------

@dataclass
class UnscheduledTask:
    task: Optional[Task] = None
    reason: str = ""
    original_priority: Optional[Priority] = None


@dataclass
class ScheduledTask:
    sched_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task: Optional[Task] = None
    pet: Optional[Pet] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    priority_score: float = 0.0
    reasoning: str = ""
    occurrence_index: int = 1  # e.g. 1-of-2 for TWICE_DAILY

    def get_duration(self) -> int:
        if self.start_time and self.end_time:
            return TimeSlot(self.start_time, self.end_time).duration_mins
        return self.task.duration_mins if self.task else 0


@dataclass
class DailyPlan:
    plan_date: Optional[date] = None
    owner: Optional[Owner] = None
    scheduled: list[ScheduledTask] = field(default_factory=list)
    unscheduled: list[UnscheduledTask] = field(default_factory=list)
    overall_reasoning: str = ""
    coverage_pct: float = 0.0

    def get_summary(self) -> str:
        total = len(self.scheduled) + len(self.unscheduled)
        mins_used = sum(st.get_duration() for st in self.scheduled)
        owner_name = self.owner.name if self.owner else "Unknown"
        lines = [
            f"Plan for {self.plan_date} — {owner_name}",
            f"Scheduled {len(self.scheduled)}/{total} tasks ({mins_used} min total)",
            f"Coverage: {self.coverage_pct:.0%}",
        ]
        if self.overall_reasoning:
            lines.append(f"Reasoning: {self.overall_reasoning}")
        if self.unscheduled:
            lines.append("Could not schedule:")
            for ut in self.unscheduled:
                task_name = ut.task.name if ut.task else "?"
                lines.append(f"  - {task_name}: {ut.reason}")
        return "\n".join(lines)

    def get_timeline(self) -> list[ScheduledTask]:
        """Return scheduled tasks sorted by start time."""
        return sorted(self.scheduled, key=lambda st: st.start_time or time(0, 0))

    def to_dict(self) -> dict:
        return {
            "plan_date": self.plan_date.isoformat() if self.plan_date else None,
            "owner": self.owner.name if self.owner else None,
            "coverage_pct": round(self.coverage_pct, 4),
            "overall_reasoning": self.overall_reasoning,
            "scheduled": [
                {
                    "task": st.task.name if st.task else None,
                    "pet": st.pet.name if st.pet else None,
                    "start": st.start_time.isoformat() if st.start_time else None,
                    "end": st.end_time.isoformat() if st.end_time else None,
                    "occurrence": (
                        f"{st.occurrence_index}/{st.task.frequency.value}"
                        if st.task else "1/1"
                    ),
                    "reasoning": st.reasoning,
                }
                for st in self.get_timeline()
            ],
            "unscheduled": [
                {
                    "task": ut.task.name if ut.task else None,
                    "reason": ut.reason,
                    "priority": ut.original_priority.name if ut.original_priority else None,
                }
                for ut in self.unscheduled
            ],
        }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

# Minimum minutes between occurrences of the same task (for multi-daily tasks)
_MIN_GAP_MINS: dict[Frequency, int] = {
    Frequency.ONCE_DAILY: 0,
    Frequency.TWICE_DAILY: 240,       # 4 hours apart
    Frequency.THREE_TIMES_DAILY: 180,  # 3 hours apart
    Frequency.WEEKLY: 0,
    Frequency.AS_NEEDED: 0,
}


class Scheduler:

    def schedule_all(self, owner: Owner, plan_date: date) -> DailyPlan:
        """
        Build a single DailyPlan covering all of the owner's pets.
        Tasks are pooled, ranked together, and placed into shared owner time —
        so cross-pet conflicts are resolved by priority.
        """
        plan = DailyPlan(plan_date=plan_date, owner=owner)
        last_placed_end: dict[str, int] = {}

        # Collect (task, pet) pairs from every pet
        all_task_pet_pairs: list[tuple[Task, Pet]] = [
            (task, pet)
            for pet in owner.pets
            for task in self._resolve_conflicts(pet.tasks)
        ]

        # Rank all tasks together by priority across all pets
        all_task_pet_pairs.sort(
            key=lambda tp: (tp[0].is_time_sensitive, tp[0].priority.value),
            reverse=True,
        )

        # Expand for frequency
        work_list: list[tuple[Task, Pet, int]] = []
        for task, pet in all_task_pet_pairs:
            count = 1 if task.frequency in (Frequency.AS_NEEDED, Frequency.WEEKLY) else task.frequency.value
            for i in range(1, count + 1):
                work_list.append((task, pet, i))

        for task, pet, occurrence_idx in work_list:
            free_slots = self._compute_free_slots(owner, plan)
            min_gap = _MIN_GAP_MINS.get(task.frequency, 0)
            last_end = last_placed_end.get(task.task_id)

            if last_end is not None and min_gap > 0:
                earliest_start = last_end + min_gap
                free_slots = _trim_slots_before(free_slots, earliest_start)

            best_slot = self.find_best_slot(task, free_slots)

            if best_slot is None:
                gap_note = (
                    f" (needs {min_gap} min gap after occurrence {occurrence_idx - 1})"
                    if last_end is not None and min_gap > 0 else ""
                )
                plan.unscheduled.append(UnscheduledTask(
                    task=task,
                    reason=f"No available slot long enough for {task.duration_mins} min{gap_note}",
                    original_priority=task.priority,
                ))
                continue

            start = self._pick_start(task, best_slot)
            end = _mins_to_time(_time_to_mins(start) + task.duration_mins)
            plan.scheduled.append(ScheduledTask(
                task=task,
                pet=pet,
                start_time=start,
                end_time=end,
                priority_score=self.score_slot(task, best_slot, owner),
                reasoning=self.explain_decision(task),
                occurrence_index=occurrence_idx,
            ))
            last_placed_end[task.task_id] = _time_to_mins(end)

        total = len(plan.scheduled) + len(plan.unscheduled)
        plan.coverage_pct = len(plan.scheduled) / total if total else 0.0
        pet_names = ", ".join(p.name for p in owner.pets)
        plan.overall_reasoning = (
            f"Scheduled {len(plan.scheduled)} task(s) across {len(owner.pets)} pet(s) "
            f"({pet_names}) using shared owner time. "
            f"{len(plan.unscheduled)} task(s) could not be placed."
        )
        return plan

    def schedule(self, owner: Owner, pet: Pet, plan_date: date) -> DailyPlan:
        """
        Build a DailyPlan for a single pet by greedily placing ranked tasks
        into the owner's free time, respecting priority and minimum spacing
        between multi-daily occurrences.
        """
        plan = DailyPlan(plan_date=plan_date, owner=owner)
        # task_id -> end-time in minutes of its most recently placed occurrence
        last_placed_end: dict[str, int] = {}

        ranked = self.rank_tasks(self._resolve_conflicts(pet.tasks))
        work_list = self._expand_by_frequency(ranked)

        for task, occurrence_idx in work_list:
            free_slots = self._compute_free_slots(owner, plan)
            min_gap = _MIN_GAP_MINS.get(task.frequency, 0)
            last_end = last_placed_end.get(task.task_id)

            # Enforce minimum spacing between occurrences of the same task
            if last_end is not None and min_gap > 0:
                earliest_start = last_end + min_gap
                free_slots = _trim_slots_before(free_slots, earliest_start)

            best_slot = self.find_best_slot(task, free_slots)

            if best_slot is None:
                gap_note = (
                    f" (needs {min_gap} min gap after occurrence {occurrence_idx - 1})"
                    if last_end is not None and min_gap > 0
                    else ""
                )
                plan.unscheduled.append(UnscheduledTask(
                    task=task,
                    reason=f"No available slot long enough for {task.duration_mins} min{gap_note}",
                    original_priority=task.priority,
                ))
                continue

            start = self._pick_start(task, best_slot)
            end = _mins_to_time(_time_to_mins(start) + task.duration_mins)
            score = self.score_slot(task, best_slot, owner)

            st = ScheduledTask(
                task=task,
                pet=pet,
                start_time=start,
                end_time=end,
                priority_score=score,
                reasoning=self.explain_decision(task),
                occurrence_index=occurrence_idx,
            )
            plan.scheduled.append(st)
            last_placed_end[task.task_id] = _time_to_mins(end)

        total = len(plan.scheduled) + len(plan.unscheduled)
        plan.coverage_pct = len(plan.scheduled) / total if total else 0.0
        plan.overall_reasoning = self._summarize_plan(plan, pet)
        return plan

    def detect_conflicts(
        self, scheduled: list[ScheduledTask]
    ) -> list[tuple[ScheduledTask, ScheduledTask]]:
        """Return every pair of scheduled tasks whose time slots overlap.

        Checks all combinations (same pet or different pets), since the owner
        can only be in one place at a time. A pair (a, b) appears once — never
        as both (a, b) and (b, a).
        """
        conflicts: list[tuple[ScheduledTask, ScheduledTask]] = []
        for i, a in enumerate(scheduled):
            # Skip tasks with no time information — they can't be compared
            if not (a.start_time and a.end_time):
                continue
            slot_a = TimeSlot(a.start_time, a.end_time)

            for b in scheduled[i + 1:]:          # i+1 avoids duplicates and self-comparison
                if not (b.start_time and b.end_time):
                    continue
                slot_b = TimeSlot(b.start_time, b.end_time)

                if slot_a.overlaps(slot_b):
                    conflicts.append((a, b))

        return conflicts

    def warn_conflicts(self, scheduled: list[ScheduledTask]) -> list[str]:
        """Return human-readable warning strings for every overlapping task pair.

        Returns an empty list when there are no conflicts — no exceptions raised,
        no program crash. The caller decides what to do with the warnings.
        """
        warnings: list[str] = []
        for a, b in self.detect_conflicts(scheduled):
            pet_a  = a.pet.name  if a.pet  else "unknown pet"
            pet_b  = b.pet.name  if b.pet  else "unknown pet"
            task_a = a.task.name if a.task else "unknown task"
            task_b = b.task.name if b.task else "unknown task"
            start_a = a.start_time.strftime("%H:%M") if a.start_time else "?"
            end_a   = a.end_time.strftime("%H:%M")   if a.end_time   else "?"
            start_b = b.start_time.strftime("%H:%M") if b.start_time else "?"
            end_b   = b.end_time.strftime("%H:%M")   if b.end_time   else "?"
            warnings.append(
                f"WARNING: '{task_a}' [{pet_a}] {start_a}–{end_a} "
                f"overlaps '{task_b}' [{pet_b}] {start_b}–{end_b}"
            )
        return warnings

    def rank_tasks(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks: time-sensitive first, then priority descending."""
        return sorted(
            tasks,
            key=lambda t: (t.is_time_sensitive, t.priority.value),
            reverse=True,
        )

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Sort tasks by preferred_window start time ascending.
        Tasks without a preferred_window are placed at the end."""
        return sorted(
            tasks,
            key=lambda t: (
                t.preferred_window.start if t.preferred_window else time(23, 59)
            ),
        )

    def score_slot(self, task: Task, slot: TimeSlot, owner: Owner) -> float:
        """
        Score a candidate time slot for a task.
        Higher score = better fit.
        """
        score = float(task.priority.value)
        if task.preferred_window:
            if slot.overlaps(task.preferred_window):
                score += 2.0
            elif task.is_time_sensitive:
                score -= 3.0  # heavy penalty: time-sensitive task placed outside window
        return score

    def find_best_slot(self, task: Task, free_slots: list[TimeSlot]) -> Optional[TimeSlot]:
        """
        Return the most suitable free slot for the task.
        Prefers slots overlapping the task's preferred_window; falls back to first fit.
        """
        candidates = [s for s in free_slots if s.duration_mins >= task.duration_mins]
        if not candidates:
            return None
        if task.preferred_window:
            overlapping = [s for s in candidates if s.overlaps(task.preferred_window)]
            if overlapping:
                return overlapping[0]
        return candidates[0]

    def explain_decision(self, task: Task) -> str:
        """Human-readable explanation of why/how a task was scheduled."""
        parts = [f"Scheduled '{task.name}' (priority: {task.priority.name})"]
        if task.is_time_sensitive:
            parts.append("time-sensitive — placed before non-urgent tasks")
        if task.preferred_window:
            pw = task.preferred_window
            parts.append(
                f"preferred window {pw.start.strftime('%H:%M')}–{pw.end.strftime('%H:%M')}"
            )
        if task.frequency not in (Frequency.ONCE_DAILY, Frequency.AS_NEEDED):
            label = task.frequency.name.lower().replace("_", " ")
            gap = _MIN_GAP_MINS[task.frequency]
            parts.append(f"repeats {label} with ≥{gap} min between occurrences")
        return "; ".join(parts)

    def _resolve_conflicts(self, tasks: list[Task]) -> list[Task]:
        """
        Drop lower-priority time-sensitive tasks whose preferred_window
        is fully blocked by a higher-priority task's window and cannot be moved.
        """
        ranked = self.rank_tasks(tasks)
        claimed_windows: list[TimeSlot] = []
        result: list[Task] = []
        for task in ranked:
            if task.is_time_sensitive and task.preferred_window:
                if any(task.preferred_window.overlaps(w) for w in claimed_windows):
                    continue  # irreconcilable conflict — lower priority loses
                claimed_windows.append(task.preferred_window)
            result.append(task)
        return result

    def _compute_free_slots(self, owner: Owner, plan: DailyPlan) -> list[TimeSlot]:
        """Owner's available slots minus what the plan has already placed."""
        return owner.get_free_time(plan.scheduled)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _expand_by_frequency(self, tasks: list[Task]) -> list[tuple[Task, int]]:
        """
        Turn each task into N (task, occurrence_index) pairs based on frequency.
        WEEKLY tasks appear once in a daily plan (today's occurrence).
        AS_NEEDED tasks appear once unless the owner has explicitly added them.
        """
        result: list[tuple[Task, int]] = []
        for task in tasks:
            if task.frequency in (Frequency.AS_NEEDED, Frequency.WEEKLY):
                count = 1
            else:
                count = task.frequency.value
            for i in range(1, count + 1):
                result.append((task, i))
        return result

    def _pick_start(self, task: Task, slot: TimeSlot) -> time:
        """
        Pick the best start time within a free slot.
        Aligns to the task's preferred_window start when possible.
        """
        if task.preferred_window and slot.overlaps(task.preferred_window):
            preferred_start_mins = max(
                _time_to_mins(slot.start),
                _time_to_mins(task.preferred_window.start),
            )
            if preferred_start_mins + task.duration_mins <= _time_to_mins(slot.end):
                return _mins_to_time(preferred_start_mins)
        return slot.start

    def _summarize_plan(self, plan: DailyPlan, pet: Pet) -> str:
        mins = sum(st.get_duration() for st in plan.scheduled)
        skipped = len(plan.unscheduled)
        return (
            f"Scheduled {len(plan.scheduled)} task(s) for {pet.name} "
            f"using {mins} min. "
            f"{skipped} task(s) could not be placed."
        )
