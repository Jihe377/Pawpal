from datetime import date, time

from pawpal_system import (
    Owner,
    Pet,
    Task,
    TaskCategory,
    Priority,
    Frequency,
    TimeSlot,
    Scheduler,
    ScheduledTask,
)

# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------

owner = Owner(
    name="Alex",
    available_slots=[TimeSlot(time(7, 0), time(21, 0))],
    timezone="America/New_York",
)

# ---------------------------------------------------------------------------
# Pets
# ---------------------------------------------------------------------------

buddy = Pet(name="Buddy", species="Dog", breed="Labrador", age_months=36, weight_kg=28.0)
luna  = Pet(name="Luna",  species="Cat", breed="Siamese",  age_months=24, weight_kg=4.5)

# ---------------------------------------------------------------------------
# Tasks for Buddy (dog) — added OUT OF ORDER intentionally
# ---------------------------------------------------------------------------

evening_walk = Task(
    name="Evening Walk",
    category=TaskCategory.WALK,
    duration_mins=45,
    priority=Priority.HIGH,
    frequency=Frequency.ONCE_DAILY,
    preferred_window=TimeSlot(time(17, 0), time(19, 0)),
    is_time_sensitive=True,
)

morning_walk = Task(
    name="Morning Walk",
    category=TaskCategory.WALK,
    duration_mins=30,
    priority=Priority.HIGH,
    frequency=Frequency.ONCE_DAILY,
    preferred_window=TimeSlot(time(7, 0), time(9, 0)),
    is_time_sensitive=True,
)

breakfast = Task(
    name="Breakfast",
    category=TaskCategory.FEEDING,
    duration_mins=10,
    priority=Priority.CRITICAL,
    frequency=Frequency.ONCE_DAILY,
    preferred_window=TimeSlot(time(7, 30), time(8, 30)),
    is_time_sensitive=True,
)

buddy.add_task(evening_walk)   # 17:00 added first
buddy.add_task(morning_walk)   # 07:00 added second
buddy.add_task(breakfast)      # 07:30 added last

# ---------------------------------------------------------------------------
# Tasks for Luna (cat) — added OUT OF ORDER intentionally
# ---------------------------------------------------------------------------

grooming = Task(
    name="Brushing",
    category=TaskCategory.GROOMING,
    duration_mins=15,
    priority=Priority.LOW,
    frequency=Frequency.ONCE_DAILY,
    preferred_window=TimeSlot(time(19, 0), time(20, 0)),
)

luna_feeding = Task(
    name="Luna Feeding",
    category=TaskCategory.FEEDING,
    duration_mins=10,
    priority=Priority.CRITICAL,
    frequency=Frequency.TWICE_DAILY,
    preferred_window=TimeSlot(time(8, 0), time(9, 0)),
    is_time_sensitive=True,
)

playtime = Task(
    name="Playtime",
    category=TaskCategory.ENRICHMENT,
    duration_mins=20,
    priority=Priority.MEDIUM,
    frequency=Frequency.ONCE_DAILY,
    preferred_window=TimeSlot(time(12, 0), time(14, 0)),
)

luna.add_task(grooming)        # 19:00 added first
luna.add_task(playtime)        # 12:00 added second
luna.add_task(luna_feeding)    # 08:00 added last

# mark one task complete so filter_tasks(is_completed=...) has something to show
morning_walk.mark_complete()

# ---------------------------------------------------------------------------
# Register pets with owner
# ---------------------------------------------------------------------------

owner.add_pet(buddy)
owner.add_pet(luna)

# ---------------------------------------------------------------------------
# Demo: sort_by_time()
# ---------------------------------------------------------------------------

scheduler = Scheduler()
all_tasks = [t for p in owner.pets for t in p.tasks]

print("=" * 50)
print("  sort_by_time() — all tasks by preferred_window")
print("=" * 50)
for t in scheduler.sort_by_time(all_tasks):
    window = (
        f"{t.preferred_window.start.strftime('%H:%M')} – "
        f"{t.preferred_window.end.strftime('%H:%M')}"
        if t.preferred_window else "no window"
    )
    print(f"  {window}  |  {t.name}")

# ---------------------------------------------------------------------------
# Demo: filter_tasks()
# ---------------------------------------------------------------------------

print()
print("=" * 50)
print("  filter_tasks(is_completed=True) — done tasks")
print("=" * 50)
for t in owner.filter_tasks(is_completed=True):
    print(f"  [DONE]  {t.name}")

print()
print("=" * 50)
print("  filter_tasks(is_completed=False) — pending tasks")
print("=" * 50)
for t in owner.filter_tasks(is_completed=False):
    print(f"  [TODO]  {t.name}")

print()
print("=" * 50)
print("  filter_tasks(pet_name='Buddy') — Buddy's tasks only")
print("=" * 50)
for t in owner.filter_tasks(pet_name="Buddy"):
    status = "DONE" if t.is_completed else "TODO"
    print(f"  [{status}]  {t.name}")

print()
print("=" * 50)
print("  filter_tasks(is_completed=False, pet_name='Luna')")
print("=" * 50)
for t in owner.filter_tasks(is_completed=False, pet_name="Luna"):
    print(f"  [TODO]  {t.name}")

# ---------------------------------------------------------------------------
# Build and print schedule
# ---------------------------------------------------------------------------

plan = scheduler.schedule_all(owner, plan_date=date.today())

print()
print("=" * 50)
print(f"  PawPal — Today's Schedule ({plan.plan_date})")
print(f"  Owner: {owner.name}")
print("=" * 50)

timeline = plan.get_timeline()
if timeline:
    for st in timeline:
        start = st.start_time.strftime("%I:%M %p") if st.start_time else "??:??"
        end   = st.end_time.strftime("%I:%M %p")   if st.end_time   else "??:??"
        pet_name  = st.pet.name  if st.pet  else "?"
        task_name = st.task.name if st.task else "?"
        category  = st.task.category.value.upper() if st.task else ""
        print(f"  {start} – {end}  |  [{pet_name}]  {task_name}  ({category})")
else:
    print("  No tasks scheduled.")

print("-" * 50)
print(f"  {len(plan.scheduled)} task(s) scheduled  |  {len(plan.unscheduled)} skipped")
print(f"  Coverage: {plan.coverage_pct:.0%}")

if plan.unscheduled:
    print("\n  Could not schedule:")
    for ut in plan.unscheduled:
        name = ut.task.name if ut.task else "?"
        print(f"    - {name}: {ut.reason}")

print("=" * 50)

# ---------------------------------------------------------------------------
# Conflict detection demo — two tasks manually forced to overlap
# ---------------------------------------------------------------------------

overlapping = [
    ScheduledTask(
        task=Task(name="Morning Walk"), pet=buddy,
        start_time=time(8, 0), end_time=time(8, 30),
    ),
    ScheduledTask(
        task=Task(name="Breakfast"), pet=buddy,
        start_time=time(8, 15), end_time=time(8, 45),   # overlaps Morning Walk
    ),
    ScheduledTask(
        task=Task(name="Luna Feeding"), pet=luna,
        start_time=time(9, 0), end_time=time(9, 10),    # no overlap
    ),
]

print()
print("=" * 50)
print("  warn_conflicts() — forced overlap scenario")
print("=" * 50)
warnings = scheduler.warn_conflicts(overlapping)
if warnings:
    for w in warnings:
        print(f"  {w}")
else:
    print("  No conflicts detected.")
print("=" * 50)
