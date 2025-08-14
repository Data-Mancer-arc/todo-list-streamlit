# app.py — 100% offline, no API keys, no external calls
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

import streamlit as st

st.set_page_config(page_title="To Do List", page_icon="✅", layout="centered")

# --------------------------
# Heuristic rules & helpers
# --------------------------

PRIORITY_KEYWORDS = {
    "high": [
        "urgent", "asap", "immediately", "deadline", "today", "tonight", "overdue",
        "submit", "payment", "invoice", "pay", "exam", "interview", "meeting",
        "presentation", "deliverable", "production", "prod", "release", "ship"
    ],
    "medium": [
        "tomorrow", "soon", "review", "draft", "report", "update", "follow up",
        "follow-up", "check in", "check-in", "milestone", "bug", "fix", "debug",
        "test", "testing", "refactor", "research", "write", "study"
    ],
    "low": [
        "someday", "when free", "ideas", "nice to have", "optional", "later",
        "clean", "organize", "backup", "grocery", "shop", "exercise", "gym",
        "read", "learn", "watch", "explore"
    ],
}

EFFORT_HINTS = {
    "low": ["email", "mail", "call", "text", "ping", "note", "rename", "move", "file", "buy", "order"],
    "medium": ["review", "draft", "write", "edit", "design", "prepare", "practice", "study", "research", "clean"],
    "high": ["implement", "build", "develop", "debug", "refactor", "deploy", "migrate", "train", "record", "configure"],
}

DATE_WORDS = {
    "today": 0,
    "tonight": 0,
    "tomorrow": 1,
    "tmrw": 1,
    "next week": 7,
    "in a week": 7,
    "in 2 days": 2,
    "in 3 days": 3,
    "this weekend": 2,
}

BULLET_SPLIT_PATTERN = re.compile(r"[\n\r]+|•|–|- |\u2022|, and | and ", re.IGNORECASE)

def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def split_tasks(raw: str) -> List[str]:
    parts = []
    for chunk in BULLET_SPLIT_PATTERN.split(raw):
        chunk = normalize_whitespace(chunk)
        if not chunk:
            continue
        if chunk.count(",") >= 2:
            parts.extend([normalize_whitespace(p) for p in chunk.split(",") if p.strip()])
        else:
            parts.append(chunk)
    return [p for p in parts if len(p) > 2]

def detect_priority(text: str) -> str:
    t = text.lower()
    score = {"high": 0, "medium": 0, "low": 0}
    for lvl, words in PRIORITY_KEYWORDS.items():
        for w in words:
            if w in t:
                score[lvl] += 1
    if score["high"] > 0:
        return "High"
    if score["medium"] > 0:
        return "Medium"
    if score["low"] > 0:
        return "Low"
    worky = any(v in t for v in (EFFORT_HINTS["medium"] + EFFORT_HINTS["high"]))
    return "Medium" if worky else "Low"

def detect_effort(text: str) -> str:
    t = text.lower()
    if any(w in t for w in EFFORT_HINTS["high"]):
        return "High"
    if any(w in t for w in EFFORT_HINTS["medium"]):
        return "Medium"
    if any(w in t for w in EFFORT_HINTS["low"]):
        return "Low"
    return "Medium"

def parse_due_date(text: str) -> Tuple[str, datetime | None]:
    t = text.lower()
    today = datetime.now().date()

    for phrase, offset in DATE_WORDS.items():
        if phrase in t:
            due = today + timedelta(days=offset)
            if phrase == "this weekend":
                dow = due.weekday()
                days_until_sat = (5 - dow) % 7
                due = today + timedelta(days=days_until_sat)
            return (due.strftime("%Y-%m-%d"), datetime.combine(due, datetime.min.time()))

    m = re.search(r"in\s+(\d{1,2})\s+day", t)
    if m:
        d = int(m.group(1))
        due = today + timedelta(days=d)
        return (due.strftime("%Y-%m-%d"), datetime.combine(due, datetime.min.time()))

    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", t)
    if m:
        y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            due = datetime(y, mo, da).date()
            return (due.strftime("%Y-%m-%d"), datetime.combine(due, datetime.min.time()))
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})", t)
    if m:
        da, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = 2000 + y if y < 100 else y
        try:
            due = datetime(y, mo, da).date()
            return (due.strftime("%Y-%m-%d"), datetime.combine(due, datetime.min.time()))
        except ValueError:
            pass

    pr = detect_priority(text)
    default_days = {"High": 0, "Medium": 3, "Low": 7}[pr]
    due = today + timedelta(days=default_days)
    return (due.strftime("%Y-%m-%d"), datetime.combine(due, datetime.min.time()))

def score_task(priority: str, due_dt: datetime | None, effort: str) -> float:
    p_map = {"High": 3.0, "Medium": 2.0, "Low": 1.0}
    e_map = {"Low": 1.25, "Medium": 1.0, "High": 0.85}
    base = p_map.get(priority, 1.5) * e_map.get(effort, 1.0)
    if due_dt:
        days = max(0.0, (due_dt.date() - datetime.now().date()).days)
        time_boost = 1.5 if days <= 0 else (1.3 if days == 1 else (1.15 if days <= 3 else 1.0))
        base *= time_boost
    return base

def build_task_row(raw: str) -> Dict[str, Any]:
    task = normalize_whitespace(raw)
    pr = detect_priority(task)
    effort = detect_effort(task)
    due_str, due_dt = parse_due_date(task)
    score = score_task(pr, due_dt, effort)
    return {
        "task": task,
        "priority": pr,
        "effort": effort,
        "due": due_str,
        "score": round(score, 3),
        "done": False,
    }

# --------------------------
# UI
# --------------------------

st.title("✅ To Do List")

if "tasks" not in st.session_state:
    st.session_state.tasks: List[Dict[str, Any]] = []

user_input = st.text_area(
    "Enter your tasks and by when they have to be completed  (comma, new line, or bullet separated):",
    placeholder="e.g., Finish EEG report today, debug PN532 UART issue, buy groceries",
    height=120,
)

col_a, col_b = st.columns(2)
with col_a:
    gen = st.button("✨ Generate from Text")
with col_b:
    clear = st.button("🧹 Clear All")

if gen:
    chunks = split_tasks(user_input)
    if not chunks:
        st.warning("I didn’t catch any tasks. Try using commas, new lines, or bullets.")
    else:
        st.session_state.tasks = [build_task_row(c) for c in chunks]

if clear:
    st.session_state.tasks = []

st.markdown("---")

# Show tasks
if st.session_state.tasks:
    sort_by = st.selectbox("Sort by", ["score (desc)", "due (asc)", "priority", "effort", "task"])
    if sort_by == "score (desc)":
        tasks_sorted = sorted(st.session_state.tasks, key=lambda x: x["score"], reverse=True)
    elif sort_by == "due (asc)":
        tasks_sorted = sorted(st.session_state.tasks, key=lambda x: x["due"])
    elif sort_by == "priority":
        order = {"High": 0, "Medium": 1, "Low": 2}
        tasks_sorted = sorted(st.session_state.tasks, key=lambda x: order.get(x["priority"], 3))
    elif sort_by == "effort":
        order = {"Low": 0, "Medium": 1, "High": 2}
        tasks_sorted = sorted(st.session_state.tasks, key=lambda x: order.get(x["effort"], 3))
    else:
        tasks_sorted = sorted(st.session_state.tasks, key=lambda x: x["task"].lower())

    to_delete = []
    for idx, row in enumerate(tasks_sorted):
        col1, col2, col3, col4, col5, col6 = st.columns([0.5, 5, 1.2, 1.2, 1.8, 0.8])
        with col1:
            chk = st.checkbox("", value=row["done"], key=f"done_{idx}")
        with col2:
            st.write(f"**{row['task']}**")
        with col3:
            st.write(f"🧯 {row['priority']}")
        with col4:
            st.write(f"⚙️ {row['effort']}")
        with col5:
            st.write(f"📅 {row['due']}")
        with col6:
            if st.button("🗑️", key=f"del_{idx}"):
                to_delete.append(idx)
        row["done"] = chk

    if to_delete:
        keep = []
        to_remove = {id(tasks_sorted[i]) for i in to_delete}
        for t in st.session_state.tasks:
            if id(t) not in to_remove:
                keep.append(t)
        st.session_state.tasks = keep

    st.markdown("---")

    if st.button("💡 Suggest Next Task"):
        remaining = [t for t in st.session_state.tasks if not t["done"]]
        if not remaining:
            st.success("Legend behavior detected. Nothing left to do. 🎉")
        else:
            for t in remaining:
                try:
                    dt = datetime.strptime(t["due"], "%Y-%m-%d")
                except Exception:
                    dt = None
                t["score"] = round(score_task(t["priority"], dt, t["effort"]), 3)
            best = sorted(remaining, key=lambda x: x["score"], reverse=True)[0]
            st.info(
                f"**Do this next:** {best['task']}  \n"
                f"_Why:_ high score from **{best['priority']}** priority, "
                f"due **{best['due']}**, and **{best['effort']}** effort."
            )
else:
    st.info("Drop your text above and press **Generate** to create a smart checklist.")
