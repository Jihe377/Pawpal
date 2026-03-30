import streamlit as st
from datetime import date, time
from pawpal_system import (
    TaskCategory, Priority, Frequency,
    TimeSlot, Constraint, Task,
    Pet, Owner, UnscheduledTask, ScheduledTask,
    DailyPlan, Scheduler,
)

_PRIORITY_MAP = {"low": Priority.LOW, "medium": Priority.MEDIUM, "high": Priority.HIGH}

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to the PawPal+ starter app.

This file is intentionally thin. It gives you a working Streamlit app so you can start quickly,
but **it does not implement the project logic**. Your job is to design the system and build it.

Use this app as your interactive demo once your backend classes/functions exist.
"""
)

with st.expander("Scenario", expanded=True):
    st.markdown(
        """
**PawPal+** is a pet care planning assistant. It helps a pet owner plan care tasks
for their pet(s) based on constraints like time, priority, and preferences.

You will design and implement the scheduling logic and connect it to this Streamlit UI.
"""
    )

with st.expander("What you need to build", expanded=True):
    st.markdown(
        """
At minimum, your system should:
- Represent pet care tasks (what needs to happen, how long it takes, priority)
- Represent the pet and the owner (basic info and preferences)
- Build a plan/schedule for a day that chooses and orders tasks based on constraints
- Explain the plan (why each task was chosen and when it happens)
"""
    )

if "owner" not in st.session_state:
    owner = Owner()
    owner.available_slots = [TimeSlot(time(8, 0), time(20, 0))]
    st.session_state.owner = owner

st.divider()

st.subheader("Owner")
owner_name = st.text_input("Owner name", value=st.session_state.owner.name or "Jordan")
if owner_name:
    st.session_state.owner.name = owner_name

st.markdown("### Add a Pet")
col1, col2 = st.columns(2)
with col1:
    pet_name = st.text_input("Pet name", value="Mochi")
with col2:
    species = st.selectbox("Species", ["dog", "cat", "other"])

if st.button("Add pet"):
    pet = Pet(name=pet_name, species=species)
    st.session_state.owner.add_pet(pet)
    st.success(f"Added {pet.name} ({pet.species})")

if st.session_state.owner.pets:
    st.write("Pets:", ", ".join(p.name for p in st.session_state.owner.pets))

st.markdown("### Add a Task")
if not st.session_state.owner.pets:
    st.info("Add a pet first before adding tasks.")
else:
    pet_names = [p.name for p in st.session_state.owner.pets]
    selected_pet_name = st.selectbox("Assign to pet", pet_names)

    col1, col2, col3 = st.columns(3)
    with col1:
        task_title = st.text_input("Task title", value="Morning walk")
    with col2:
        duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
    with col3:
        priority_str = st.selectbox("Priority", ["low", "medium", "high"], index=2)

    if st.button("Add task"):
        target_pet = next(p for p in st.session_state.owner.pets if p.name == selected_pet_name)
        task = Task(name=task_title, duration_mins=int(duration), priority=_PRIORITY_MAP[priority_str])
        target_pet.add_task(task)
        st.success(f"Added task '{task.name}' to {target_pet.name}")

    all_tasks = [(p.name, t) for p in st.session_state.owner.pets for t in p.tasks]
    if all_tasks:
        st.write("Current tasks:")
        st.table([
            {"pet": pname, "task": t.name, "duration (min)": t.duration_mins, "priority": t.priority.name}
            for pname, t in all_tasks
        ])
    else:
        st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")

if st.button("Generate schedule"):
    owner = st.session_state.owner
    if not owner.pets or not any(p.tasks for p in owner.pets):
        st.warning("Add at least one pet with one task before generating a schedule.")
    else:
        plan = Scheduler().schedule_all(owner, date.today())
        st.success(plan.get_summary())

        if plan.scheduled:
            st.markdown("#### Scheduled Tasks")
            st.table([
                {
                    "pet": st.pet.name if st.pet else "—",
                    "task": st.task.name if st.task else "—",
                    "start": st.start_time.strftime("%H:%M") if st.start_time else "—",
                    "end": st.end_time.strftime("%H:%M") if st.end_time else "—",
                    "reasoning": st.reasoning,
                }
                for st in plan.get_timeline()
            ])

        if plan.unscheduled:
            st.markdown("#### Could Not Schedule")
            st.table([
                {"task": ut.task.name if ut.task else "—", "reason": ut.reason}
                for ut in plan.unscheduled
            ])
