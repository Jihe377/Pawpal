import pytest
from datetime import date, time

from pawpal_system import (
    Frequency,
    Owner,
    Pet,
    Priority,
    Scheduler,
    ScheduledTask,
    Task,
    TaskCategory,
    TimeSlot,
    _time_to_mins,
    _mins_to_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_owner(start="07:00", end="21:00") -> Owner:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return Owner(
        name="Test Owner",
        available_slots=[TimeSlot(time(sh, sm), time(eh, em))],
    )


def make_task(
    name="Walk",
    category=TaskCategory.WALK,
    duration_mins=30,
    priority=Priority.MEDIUM,
    frequency=Frequency.ONCE_DAILY,
    preferred_window=None,
    is_time_sensitive=False,
) -> Task:
    return Task(
        name=name,
        category=category,
        duration_mins=duration_mins,
        priority=priority,
        frequency=frequency,
        preferred_window=preferred_window,
        is_time_sensitive=is_time_sensitive,
    )


def make_pet(name="Buddy", tasks=None) -> Pet:
    pet = Pet(name=name, species="Dog", breed="Lab", age_months=12, weight_kg=20.0)
    for t in (tasks or []):
        pet.add_task(t)
    return pet


TODAY = date(2026, 3, 29)


# ---------------------------------------------------------------------------
# TimeSlot
# ---------------------------------------------------------------------------

class TestTimeSlot:
    def test_valid_slot(self):
        ts = TimeSlot(time(8, 0), time(9, 0))
        assert ts.duration_mins == 60

    def test_invalid_slot_raises(self):
        with pytest.raises(ValueError):
            TimeSlot(time(9, 0), time(8, 0))

    def test_equal_times_raises(self):
        with pytest.raises(ValueError):
            TimeSlot(time(8, 0), time(8, 0))

    def test_overlaps_true(self):
        a = TimeSlot(time(8, 0), time(10, 0))
        b = TimeSlot(time(9, 0), time(11, 0))
        assert a.overlaps(b)
        assert b.overlaps(a)

    def test_overlaps_false_adjacent(self):
        a = TimeSlot(time(8, 0), time(9, 0))
        b = TimeSlot(time(9, 0), time(10, 0))
        assert not a.overlaps(b)

    def test_overlaps_false_disjoint(self):
        a = TimeSlot(time(8, 0), time(9, 0))
        b = TimeSlot(time(10, 0), time(11, 0))
        assert not a.overlaps(b)

    def test_contains(self):
        ts = TimeSlot(time(8, 0), time(10, 0))
        assert ts.contains(time(9, 0))
        assert not ts.contains(time(10, 0))  # end is exclusive
        assert not ts.contains(time(7, 59))

    def test_to_dict(self):
        ts = TimeSlot(time(8, 0), time(9, 30))
        d = ts.to_dict()
        assert d["start"] == "08:00:00"
        assert d["end"] == "09:30:00"

    def test_duration_mins(self):
        ts = TimeSlot(time(8, 0), time(8, 45))
        assert ts.duration_mins == 45


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class TestTimeHelpers:
    def test_time_to_mins(self):
        assert _time_to_mins(time(8, 30)) == 510

    def test_mins_to_time(self):
        assert _mins_to_time(510) == time(8, 30)

    def test_roundtrip(self):
        t = time(14, 45)
        assert _mins_to_time(_time_to_mins(t)) == t


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class TestTask:
    def test_valid_task(self):
        task = make_task()
        assert task.validate()

    def test_invalid_empty_name(self):
        task = make_task(name="  ")
        assert not task.validate()

    def test_invalid_zero_duration(self):
        task = make_task(duration_mins=0)
        assert not task.validate()

    def test_invalid_window_shorter_than_duration(self):
        task = make_task(
            duration_mins=60,
            preferred_window=TimeSlot(time(8, 0), time(8, 30)),
        )
        assert not task.validate()

    def test_valid_window_fits(self):
        task = make_task(
            duration_mins=30,
            preferred_window=TimeSlot(time(8, 0), time(9, 0)),
        )
        assert task.validate()

    def test_mark_complete(self):
        task = make_task()
        assert not task.is_completed
        task.mark_complete()
        assert task.is_completed

    def test_unique_ids(self):
        t1, t2 = make_task(), make_task()
        assert t1.task_id != t2.task_id


# ---------------------------------------------------------------------------
# Pet
# ---------------------------------------------------------------------------

class TestPet:
    def test_add_task(self):
        pet = make_pet()
        task = make_task()
        pet.add_task(task)
        assert task in pet.tasks

    def test_remove_task(self):
        task = make_task()
        pet = make_pet(tasks=[task])
        pet.remove_task(task.task_id)
        assert pet.tasks == []

    def test_remove_nonexistent_task_noop(self):
        task = make_task()
        pet = make_pet(tasks=[task])
        pet.remove_task("nonexistent-id")
        assert len(pet.tasks) == 1

    def test_get_tasks_by_category(self):
        walk = make_task(name="Walk", category=TaskCategory.WALK)
        feed = make_task(name="Feed", category=TaskCategory.FEEDING)
        pet = make_pet(tasks=[walk, feed])
        assert pet.get_tasks_by_category(TaskCategory.WALK) == [walk]
        assert pet.get_tasks_by_category(TaskCategory.FEEDING) == [feed]
        assert pet.get_tasks_by_category(TaskCategory.MEDICATION) == []


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------

class TestOwner:
    def test_add_pet(self):
        owner = make_owner()
        pet = make_pet()
        owner.add_pet(pet)
        assert pet in owner.pets

    def test_remove_pet(self):
        pet = make_pet()
        owner = make_owner()
        owner.add_pet(pet)
        owner.remove_pet(pet.pet_id)
        assert owner.pets == []

    def test_get_free_time_no_scheduled(self):
        owner = make_owner("08:00", "10:00")
        free = owner.get_free_time([])
        assert len(free) == 1
        assert free[0].start == time(8, 0)
        assert free[0].end == time(10, 0)

    def test_get_free_time_subtracts_scheduled(self):
        owner = make_owner("08:00", "10:00")
        task = make_task(duration_mins=60)
        st = ScheduledTask(
            task=task,
            start_time=time(8, 0),
            end_time=time(9, 0),
        )
        free = owner.get_free_time([st])
        assert len(free) == 1
        assert free[0].start == time(9, 0)
        assert free[0].end == time(10, 0)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class TestScheduler:
    def setup_method(self):
        self.scheduler = Scheduler()

    def test_rank_tasks_time_sensitive_first(self):
        normal = make_task(name="Normal", priority=Priority.HIGH)
        urgent = make_task(name="Urgent", priority=Priority.LOW, is_time_sensitive=True)
        ranked = self.scheduler.rank_tasks([normal, urgent])
        assert ranked[0].name == "Urgent"

    def test_rank_tasks_priority_order(self):
        low = make_task(name="Low", priority=Priority.LOW)
        high = make_task(name="High", priority=Priority.HIGH)
        ranked = self.scheduler.rank_tasks([low, high])
        assert ranked[0].name == "High"

    def test_find_best_slot_returns_none_when_no_fit(self):
        task = make_task(duration_mins=120)
        slots = [TimeSlot(time(8, 0), time(8, 30))]
        assert self.scheduler.find_best_slot(task, slots) is None

    def test_find_best_slot_prefers_preferred_window(self):
        task = make_task(
            duration_mins=30,
            preferred_window=TimeSlot(time(14, 0), time(16, 0)),
        )
        morning = TimeSlot(time(8, 0), time(12, 0))
        afternoon = TimeSlot(time(14, 0), time(17, 0))
        best = self.scheduler.find_best_slot(task, [morning, afternoon])
        assert best == afternoon

    def test_find_best_slot_falls_back_to_first_fit(self):
        task = make_task(duration_mins=30)
        slots = [TimeSlot(time(8, 0), time(10, 0))]
        best = self.scheduler.find_best_slot(task, slots)
        assert best == slots[0]

    def test_schedule_places_task(self):
        owner = make_owner()
        task = make_task(duration_mins=30)
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        assert len(plan.scheduled) == 1
        assert plan.scheduled[0].task.name == "Walk"

    def test_schedule_respects_preferred_window(self):
        owner = make_owner()
        task = make_task(
            duration_mins=30,
            preferred_window=TimeSlot(time(14, 0), time(16, 0)),
        )
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        assert len(plan.scheduled) == 1
        st = plan.scheduled[0]
        assert st.start_time >= time(14, 0)

    def test_schedule_unscheduled_when_no_time(self):
        owner = make_owner("08:00", "08:10")  # only 10 min available
        task = make_task(duration_mins=60)
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        assert len(plan.scheduled) == 0
        assert len(plan.unscheduled) == 1

    def test_schedule_twice_daily_places_two(self):
        owner = make_owner("07:00", "21:00")
        task = make_task(duration_mins=10, frequency=Frequency.TWICE_DAILY)
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        assert len(plan.scheduled) == 2

    def test_schedule_twice_daily_gap_enforced(self):
        owner = make_owner("07:00", "21:00")
        task = make_task(duration_mins=10, frequency=Frequency.TWICE_DAILY)
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        times = sorted(plan.scheduled, key=lambda s: s.start_time)
        gap = _time_to_mins(times[1].start_time) - _time_to_mins(times[0].end_time)
        assert gap >= 240  # 4-hour minimum

    def test_schedule_all_multiple_pets(self):
        owner = make_owner()
        pet1 = make_pet(name="Buddy", tasks=[make_task(name="Walk Buddy")])
        pet2 = make_pet(name="Luna", tasks=[make_task(name="Feed Luna", category=TaskCategory.FEEDING)])
        owner.add_pet(pet1)
        owner.add_pet(pet2)
        plan = self.scheduler.schedule_all(owner, TODAY)
        pet_names = {st.pet.name for st in plan.scheduled}
        assert "Buddy" in pet_names
        assert "Luna" in pet_names

    def test_coverage_pct_all_scheduled(self):
        owner = make_owner()
        task = make_task(duration_mins=30)
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        assert plan.coverage_pct == 1.0

    def test_coverage_pct_none_scheduled(self):
        owner = make_owner("08:00", "08:05")
        task = make_task(duration_mins=60)
        pet = make_pet(tasks=[task])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        assert plan.coverage_pct == 0.0

    def test_get_timeline_sorted(self):
        owner = make_owner()
        t1 = make_task(name="Late",  duration_mins=30, preferred_window=TimeSlot(time(18, 0), time(19, 0)))
        t2 = make_task(name="Early", duration_mins=30, preferred_window=TimeSlot(time(8, 0),  time(9, 0)))
        pet = make_pet(tasks=[t1, t2])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        timeline = plan.get_timeline()
        assert timeline[0].task.name == "Early"
        assert timeline[1].task.name == "Late"


# ---------------------------------------------------------------------------
# DailyPlan.get_summary
# ---------------------------------------------------------------------------

class TestDailyPlanSummary:
    def test_summary_contains_owner_name(self):
        owner = make_owner()
        task = make_task()
        pet = make_pet(tasks=[task])
        owner.add_pet(pet)
        plan = Scheduler().schedule_all(owner, TODAY)
        summary = plan.get_summary()
        assert "Test Owner" in summary

    def test_summary_contains_date(self):
        owner = make_owner()
        plan = Scheduler().schedule_all(owner, TODAY)
        assert str(TODAY) in plan.get_summary()
