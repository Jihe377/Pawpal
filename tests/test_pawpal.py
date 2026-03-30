import pytest
from datetime import date, time

from pawpal_system import (
    Constraint,
    DailyPlan,
    Frequency,
    Owner,
    Pet,
    Priority,
    Scheduler,
    ScheduledTask,
    Task,
    TaskCategory,
    TimeSlot,
    UnscheduledTask,
    _mins_to_time,
    _subtract_booked,
    _time_to_mins,
    _trim_slots_before,
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


# ---------------------------------------------------------------------------
# Sorting Correctness
# ---------------------------------------------------------------------------

class TestSortingCorrectness:
    def setup_method(self):
        self.scheduler = Scheduler()

    def test_sort_by_time_chronological_order(self):
        afternoon = make_task(name="Afternoon", preferred_window=TimeSlot(time(14, 0), time(15, 0)))
        morning   = make_task(name="Morning",   preferred_window=TimeSlot(time(8,  0), time(9,  0)))
        noon      = make_task(name="Noon",       preferred_window=TimeSlot(time(12, 0), time(13, 0)))
        result = self.scheduler.sort_by_time([afternoon, morning, noon])
        assert [t.name for t in result] == ["Morning", "Noon", "Afternoon"]

    def test_sort_by_time_no_window_goes_to_end(self):
        no_window = make_task(name="NoWindow")
        morning   = make_task(name="Morning", preferred_window=TimeSlot(time(8, 0), time(9, 0)))
        result = self.scheduler.sort_by_time([no_window, morning])
        assert result[0].name == "Morning"
        assert result[1].name == "NoWindow"

    def test_sort_by_time_all_no_window_returns_all(self):
        """All tasks without windows should be returned — none dropped."""
        tasks = [make_task(name=n) for n in ("A", "B", "C")]
        result = self.scheduler.sort_by_time(tasks)
        assert len(result) == 3
        assert {t.name for t in result} == {"A", "B", "C"}

    def test_get_timeline_returns_chronological_order(self):
        owner = make_owner()
        late  = make_task(name="Late",  duration_mins=30, preferred_window=TimeSlot(time(18, 0), time(19, 0)))
        early = make_task(name="Early", duration_mins=30, preferred_window=TimeSlot(time(8,  0), time(9,  0)))
        mid   = make_task(name="Mid",   duration_mins=30, preferred_window=TimeSlot(time(12, 0), time(13, 0)))
        pet = make_pet(tasks=[late, early, mid])
        plan = Scheduler().schedule(owner, pet, TODAY)
        starts = [st.start_time for st in plan.get_timeline()]
        assert starts == sorted(starts)

    def test_get_timeline_none_start_time_sorts_first(self):
        """ScheduledTasks with None start_time are treated as time(0,0) and sort first."""
        st_timed   = ScheduledTask(start_time=time(10, 0), end_time=time(11, 0))
        st_no_time = ScheduledTask(start_time=None, end_time=None)
        plan = DailyPlan(plan_date=TODAY, scheduled=[st_timed, st_no_time])
        assert plan.get_timeline()[0] is st_no_time

    def test_rank_tasks_does_not_drop_equal_priority(self):
        """rank_tasks must return all tasks even when priorities are identical."""
        tasks = [make_task(name=f"T{i}", priority=Priority.MEDIUM) for i in range(5)]
        ranked = self.scheduler.rank_tasks(tasks)
        assert len(ranked) == 5
        assert {t.name for t in ranked} == {t.name for t in tasks}


# ---------------------------------------------------------------------------
# Recurrence Logic
# ---------------------------------------------------------------------------

class TestRecurrenceLogic:
    def test_daily_creates_next_day(self):
        task = Task(name="Feed", frequency=Frequency.ONCE_DAILY, duration_mins=15,
                    due_date=date(2026, 3, 29))
        assert task.mark_complete().due_date == date(2026, 3, 30)

    def test_weekly_creates_next_week(self):
        task = Task(name="Vet", frequency=Frequency.WEEKLY, duration_mins=60,
                    due_date=date(2026, 3, 29))
        assert task.mark_complete().due_date == date(2026, 4, 5)

    def test_twice_daily_advances_one_day(self):
        """TWICE_DAILY recurs daily (next morning), not every 12 h."""
        task = Task(name="Meds", frequency=Frequency.TWICE_DAILY, duration_mins=10,
                    due_date=date(2026, 3, 29))
        assert task.mark_complete().due_date == date(2026, 3, 30)

    def test_three_times_daily_advances_one_day(self):
        task = Task(name="Insulin", frequency=Frequency.THREE_TIMES_DAILY, duration_mins=5,
                    due_date=date(2026, 3, 29))
        assert task.mark_complete().due_date == date(2026, 3, 30)

    def test_as_needed_returns_none(self):
        task = Task(name="Bath", frequency=Frequency.AS_NEEDED, duration_mins=30)
        assert task.mark_complete() is None

    def test_original_task_flagged_complete(self):
        task = Task(name="Walk", frequency=Frequency.ONCE_DAILY, duration_mins=30, due_date=TODAY)
        task.mark_complete()
        assert task.is_completed is True

    def test_next_task_not_completed(self):
        task = Task(name="Walk", frequency=Frequency.ONCE_DAILY, duration_mins=30, due_date=TODAY)
        assert task.mark_complete().is_completed is False

    def test_next_task_gets_new_id(self):
        task = Task(name="Walk", frequency=Frequency.ONCE_DAILY, duration_mins=30, due_date=TODAY)
        assert task.mark_complete().task_id != task.task_id

    def test_mark_complete_preserves_attributes(self):
        window = TimeSlot(time(8, 0), time(9, 0))
        task = Task(
            name="Medication", category=TaskCategory.MEDICATION,
            duration_mins=10, priority=Priority.CRITICAL,
            frequency=Frequency.TWICE_DAILY, preferred_window=window,
            is_time_sensitive=True, notes="Give with food", due_date=TODAY,
        )
        nxt = task.mark_complete()
        assert nxt.name == "Medication"
        assert nxt.category == TaskCategory.MEDICATION
        assert nxt.duration_mins == 10
        assert nxt.priority == Priority.CRITICAL
        assert nxt.frequency == Frequency.TWICE_DAILY
        assert nxt.preferred_window == window
        assert nxt.is_time_sensitive is True
        assert nxt.notes == "Give with food"

    def test_no_due_date_falls_back_to_today(self):
        """When due_date is None, next due_date is based on date.today() — not None."""
        task = Task(name="Walk", frequency=Frequency.ONCE_DAILY, duration_mins=30)
        nxt = task.mark_complete()
        assert nxt is not None
        assert nxt.due_date is not None
        assert nxt.due_date > date.today()


# ---------------------------------------------------------------------------
# Conflict Detection
# ---------------------------------------------------------------------------

class TestConflictDetection:
    def setup_method(self):
        self.scheduler = Scheduler()

    def _st(self, name, start, end, pet_name="Buddy") -> ScheduledTask:
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        return ScheduledTask(
            task=make_task(name=name),
            pet=make_pet(name=pet_name),
            start_time=time(sh, sm),
            end_time=time(eh, em),
        )

    def test_overlapping_pair_detected(self):
        a = self._st("A", "08:00", "09:30")
        b = self._st("B", "09:00", "10:00")
        assert self.scheduler.detect_conflicts([a, b]) == [(a, b)]

    def test_adjacent_slots_not_a_conflict(self):
        a = self._st("A", "08:00", "09:00")
        b = self._st("B", "09:00", "10:00")
        assert self.scheduler.detect_conflicts([a, b]) == []

    def test_disjoint_slots_not_a_conflict(self):
        a = self._st("A", "08:00", "09:00")
        b = self._st("B", "10:00", "11:00")
        assert self.scheduler.detect_conflicts([a, b]) == []

    def test_tasks_without_times_skipped(self):
        no_time = ScheduledTask(task=make_task(name="NoTime"))
        timed   = self._st("Timed", "09:00", "10:00")
        assert self.scheduler.detect_conflicts([no_time, timed]) == []

    def test_pair_reported_once_not_twice(self):
        """(a, b) should appear once — never both (a, b) and (b, a)."""
        a = self._st("A", "08:00", "10:00")
        b = self._st("B", "09:00", "11:00")
        assert len(self.scheduler.detect_conflicts([a, b])) == 1

    def test_three_way_overlap_yields_three_pairs(self):
        a = self._st("A", "08:00", "11:00")
        b = self._st("B", "09:00", "12:00")
        c = self._st("C", "10:00", "13:00")
        assert len(self.scheduler.detect_conflicts([a, b, c])) == 3

    def test_warn_conflicts_returns_warning_strings(self):
        a = self._st("Walk",  "08:00", "09:30", pet_name="Buddy")
        b = self._st("Feed",  "09:00", "10:00", pet_name="Luna")
        warnings = self.scheduler.warn_conflicts([a, b])
        assert len(warnings) == 1
        assert "Walk" in warnings[0] and "Feed" in warnings[0]

    def test_warn_conflicts_empty_when_no_overlap(self):
        a = self._st("A", "08:00", "09:00")
        b = self._st("B", "09:00", "10:00")
        assert self.scheduler.warn_conflicts([a, b]) == []

    def test_warn_conflicts_cross_pet(self):
        """Overlapping tasks assigned to different pets should still be flagged."""
        a = self._st("Walk Buddy", "08:00", "09:00", pet_name="Buddy")
        b = self._st("Walk Luna",  "08:30", "09:30", pet_name="Luna")
        assert len(self.scheduler.warn_conflicts([a, b])) == 1

    def test_scheduler_produces_no_conflicts_for_single_pet(self):
        """schedule() should never produce self-conflicting output."""
        owner = make_owner()
        tasks = [
            make_task(name="Walk",    duration_mins=30, frequency=Frequency.TWICE_DAILY),
            make_task(name="Feed",    duration_mins=15, frequency=Frequency.THREE_TIMES_DAILY),
            make_task(name="Groom",   duration_mins=20),
        ]
        pet = make_pet(tasks=tasks)
        plan = Scheduler().schedule(owner, pet, TODAY)
        assert self.scheduler.detect_conflicts(plan.scheduled) == []


# ---------------------------------------------------------------------------
# Edge Cases — slot arithmetic
# ---------------------------------------------------------------------------

class TestSlotArithmetic:
    def test_subtract_booked_adjacent_leaves_slot_unchanged(self):
        """Booked slot that touches but doesn't overlap should not shrink the free slot."""
        free   = [TimeSlot(time(8, 0), time(9, 0))]
        booked =  TimeSlot(time(9, 0), time(10, 0))
        result = _subtract_booked(free, booked)
        assert result == [TimeSlot(time(8, 0), time(9, 0))]

    def test_subtract_booked_fully_consuming_returns_empty(self):
        free   = [TimeSlot(time(8, 0), time(9, 0))]
        booked =  TimeSlot(time(7, 0), time(10, 0))
        assert _subtract_booked(free, booked) == []

    def test_subtract_booked_splits_in_middle(self):
        free   = [TimeSlot(time(8, 0), time(12, 0))]
        booked =  TimeSlot(time(9, 0), time(11, 0))
        result = _subtract_booked(free, booked)
        assert result == [TimeSlot(time(8, 0), time(9, 0)), TimeSlot(time(11, 0), time(12, 0))]

    def test_trim_slots_before_past_all_slots_returns_empty(self):
        slots = [TimeSlot(time(8, 0), time(10, 0))]
        assert _trim_slots_before(slots, _time_to_mins(time(11, 0))) == []

    def test_trim_slots_before_trims_partial(self):
        slots  = [TimeSlot(time(8, 0), time(12, 0))]
        result = _trim_slots_before(slots, _time_to_mins(time(10, 0)))
        assert result == [TimeSlot(time(10, 0), time(12, 0))]

    def test_trim_slots_before_at_slot_end_drops_slot(self):
        """earliest_mins == slot end means zero usable time — slot should be dropped."""
        slots = [TimeSlot(time(8, 0), time(10, 0))]
        assert _trim_slots_before(slots, _time_to_mins(time(10, 0))) == []


# ---------------------------------------------------------------------------
# Edge Cases — gap enforcement near day boundary
# ---------------------------------------------------------------------------

class TestGapEnforcement:
    def test_twice_daily_second_occurrence_unscheduled_when_gap_impossible(self):
        """First occurrence placed near end of day; 4 h gap pushes second past midnight → unscheduled."""
        owner = make_owner("19:00", "23:59")
        task  = make_task(name="Meds", duration_mins=30, frequency=Frequency.TWICE_DAILY)
        pet   = make_pet(tasks=[task])
        plan  = Scheduler().schedule(owner, pet, TODAY)
        assert len(plan.scheduled)   == 1
        assert len(plan.unscheduled) == 1

    def test_three_times_daily_all_placed_with_wide_window(self):
        owner = make_owner("06:00", "22:00")
        task  = make_task(name="Insulin", duration_mins=5, frequency=Frequency.THREE_TIMES_DAILY)
        pet   = make_pet(tasks=[task])
        plan  = Scheduler().schedule(owner, pet, TODAY)
        assert len(plan.scheduled) == 3

    def test_three_times_daily_gaps_enforced(self):
        owner = make_owner("06:00", "22:00")
        task  = make_task(name="Insulin", duration_mins=5, frequency=Frequency.THREE_TIMES_DAILY)
        pet   = make_pet(tasks=[task])
        plan  = Scheduler().schedule(owner, pet, TODAY)
        times = sorted(plan.scheduled, key=lambda s: s.start_time)
        for i in range(1, len(times)):
            gap = _time_to_mins(times[i].start_time) - _time_to_mins(times[i - 1].end_time)
            assert gap >= 180


# ---------------------------------------------------------------------------
# Edge Cases — resolve_conflicts
# ---------------------------------------------------------------------------

class TestResolveConflicts:
    def setup_method(self):
        self.scheduler = Scheduler()

    def test_lower_priority_time_sensitive_dropped(self):
        window = TimeSlot(time(8, 0), time(9, 0))
        high = make_task(name="High", priority=Priority.CRITICAL, is_time_sensitive=True,
                         preferred_window=window, duration_mins=30)
        low  = make_task(name="Low",  priority=Priority.LOW,      is_time_sensitive=True,
                         preferred_window=window, duration_mins=30)
        kept, dropped = self.scheduler._resolve_conflicts([high, low])
        assert [t.name for t in kept]    == ["High"]
        assert [t.name for t in dropped] == ["Low"]

    def test_non_time_sensitive_overlap_not_dropped(self):
        """Non-time-sensitive tasks with overlapping windows compete normally; neither is dropped."""
        window = TimeSlot(time(8, 0), time(9, 0))
        t1 = make_task(name="T1", is_time_sensitive=False, preferred_window=window, duration_mins=30)
        t2 = make_task(name="T2", is_time_sensitive=False, preferred_window=window, duration_mins=30)
        kept, dropped = self.scheduler._resolve_conflicts([t1, t2])
        assert len(kept) == 2
        assert len(dropped) == 0

    def test_dropped_task_appears_in_unscheduled(self):
        window = TimeSlot(time(8, 0), time(9, 0))
        owner  = make_owner()
        high = make_task(name="High", priority=Priority.CRITICAL, is_time_sensitive=True,
                         preferred_window=window, duration_mins=30)
        low  = make_task(name="Low",  priority=Priority.LOW,      is_time_sensitive=True,
                         preferred_window=window, duration_mins=30)
        pet  = make_pet(tasks=[high, low])
        plan = self.scheduler.schedule(owner, pet, TODAY)
        unscheduled_names = [ut.task.name for ut in plan.unscheduled if ut.task]
        assert "Low" in unscheduled_names


# ---------------------------------------------------------------------------
# Edge Cases — coverage and serialisation
# ---------------------------------------------------------------------------

class TestCoverageAndSerialisation:
    def test_coverage_pct_zero_tasks_no_division_error(self):
        plan = Scheduler().schedule(make_owner(), make_pet(tasks=[]), TODAY)
        assert plan.coverage_pct == 0.0

    def test_to_dict_as_needed_occurrence_string(self):
        """AS_NEEDED has frequency.value == 0, so occurrence should render as '1/0'."""
        owner = make_owner()
        task  = make_task(name="Bath", frequency=Frequency.AS_NEEDED, duration_mins=30)
        pet   = make_pet(tasks=[task])
        plan  = Scheduler().schedule(owner, pet, TODAY)
        d = plan.to_dict()
        assert len(d["scheduled"]) == 1
        assert d["scheduled"][0]["occurrence"] == "1/0"

    def test_to_dict_keys_present(self):
        plan = Scheduler().schedule(make_owner(), make_pet(tasks=[make_task()]), TODAY)
        d = plan.to_dict()
        for key in ("plan_date", "owner", "scheduled", "unscheduled", "coverage_pct"):
            assert key in d


# ---------------------------------------------------------------------------
# Edge Cases — Constraint
# ---------------------------------------------------------------------------

class TestConstraint:
    def test_within_daily_budget_passes(self):
        st = ScheduledTask(task=make_task(duration_mins=30),
                           start_time=time(8, 0), end_time=time(8, 30))
        assert Constraint(max_daily_minutes=480).validate([st]) is True

    def test_over_daily_budget_fails(self):
        st = ScheduledTask(task=make_task(duration_mins=30),
                           start_time=time(8, 0), end_time=time(8, 30))
        assert Constraint(max_daily_minutes=10).validate([st]) is False

    def test_task_in_blocked_slot_fails(self):
        st = ScheduledTask(task=make_task(duration_mins=30),
                           start_time=time(8, 30), end_time=time(9, 0))
        constraint = Constraint(blocked_slots=[TimeSlot(time(8, 0), time(10, 0))])
        assert constraint.validate([st]) is False

    def test_excluded_task_id_fails(self):
        task = make_task(duration_mins=30)
        st   = ScheduledTask(task=task, start_time=time(8, 0), end_time=time(8, 30))
        assert Constraint(task_exclusions=[task.task_id]).validate([st]) is False

    def test_get_available_slots_excludes_blocked(self):
        blocked   = TimeSlot(time(10, 0), time(12, 0))
        available = Constraint(blocked_slots=[blocked]).get_available_slots([])
        for slot in available:
            assert not slot.overlaps(blocked)

    def test_max_consecutive_mins_enforced(self):
        st = ScheduledTask(task=make_task(duration_mins=90),
                           start_time=time(8, 0), end_time=time(9, 30))
        assert Constraint(max_consecutive_mins=30).validate([st]) is False

    def test_max_consecutive_mins_back_to_back_tasks(self):
        """Two adjacent 20-min tasks should fail a 30-min consecutive limit."""
        t1 = ScheduledTask(task=make_task(duration_mins=20),
                           start_time=time(8, 0), end_time=time(8, 20))
        t2 = ScheduledTask(task=make_task(duration_mins=20),
                           start_time=time(8, 20), end_time=time(8, 40))
        assert Constraint(max_consecutive_mins=30).validate([t1, t2]) is False

    def test_max_consecutive_mins_with_gap_passes(self):
        """Two 20-min tasks separated by a gap should pass a 30-min consecutive limit."""
        t1 = ScheduledTask(task=make_task(duration_mins=20),
                           start_time=time(8, 0), end_time=time(8, 20))
        t2 = ScheduledTask(task=make_task(duration_mins=20),
                           start_time=time(9, 0), end_time=time(9, 20))
        assert Constraint(max_consecutive_mins=30).validate([t1, t2]) is True
