from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
import json, pathlib, uuid

app = FastAPI(title="AI Mentor - MVP")

DATA = json.loads((pathlib.Path(__file__).parent/"data"/"courses.json").read_text(encoding="utf-8"))
COURSES = {c["code"]: c for c in DATA}

Day = Literal["SUN","MON","TUE","WED","THU","FRI"]

class ClassSlot(BaseModel):
    type: Literal["lecture","tutorial","lab"] = "lecture"
    day: Day
    start: str
    end: str
    room: Optional[str] = None

class Constraints(BaseModel):
    max_credits: Optional[int] = 22
    busy_days: List[Day] = []
    avoid_times: List[str] = []   # e.g. ["TUE 13:00-15:00"]
    free_day: Optional[Day] = None
    morning_only: bool = False

class BuildScheduleIn(BaseModel):
    courses: List[str] = Field(..., description="Course codes to consider")
    constraints: Constraints = Constraints()

class TimeTable(BaseModel):
    selected: List[Dict[str, Any]]
    credits: int
    notes: Optional[str] = None

class BuildScheduleOut(BaseModel):
    timetable: TimeTable
    alternatives: List[TimeTable] = []

class CalendarIn(BaseModel):
    timetable: Dict[str, Any]
    provider: Literal["google","mock"] = "mock"

class ReminderIn(BaseModel):
    topic: str
    when: str
    channel: Literal["mock","email","push"] = "mock"

def to_minutes(hhmm: str) -> int:
    h,m = map(int, hhmm.split(":")); return h*60+m

def overlap(a: ClassSlot, b: ClassSlot) -> bool:
    if a.day != b.day: return False
    return max(to_minutes(a.start), to_minutes(b.start)) < min(to_minutes(a.end), to_minutes(b.end))

def violates_avoid(slot: ClassSlot, avoid: List[str]) -> bool:
    for rule in avoid:
        try:
            d, times = rule.split(" ")
            s,e = times.split("-")
            probe = ClassSlot(day=d, start=s, end=e)
            if slot.day == d and overlap(slot, probe):
                return True
        except:
            pass
    return False

def credits_of(selection: List[str]) -> int:
    return sum(COURSES[c]["credits"] for c in selection)

def schedule_greedy(course_codes: List[str], cons: Constraints):
    chosen, slots = [], []
    for code in course_codes:
        c = COURSES.get(code)
        if not c: continue
        if any(s.get("day") in cons.busy_days for s in c.get("classes", [])):
            continue
        if cons.morning_only and any(to_minutes(s["end"]) > 12*60 for s in c.get("classes", [])):
            continue
        conflict = False
        for s in c.get("classes", []):
            cs = ClassSlot(**{**s, "type": s.get("type","lecture")})
            if violates_avoid(cs, cons.avoid_times): conflict = True; break
            for used in slots:
                if overlap(cs, used): conflict = True; break
            if conflict: break
        if conflict: continue
        chosen.append(code)
        slots.extend([ClassSlot(**{**s, "type": s.get("type","lecture")}) for s in c.get("classes", [])])
        if credits_of(chosen) >= (cons.max_credits or 99):
            break
    return chosen, slots

@app.get("/health")
def health(): return {"ok": True}

@app.post("/tools/buildSchedule", response_model=BuildScheduleOut)
def build_schedule(inp: BuildScheduleIn):
    base = [c for c in inp.courses if c in COURSES]
    if not base: raise HTTPException(400, "No valid courses")
    chosen, _ = schedule_greedy(base, inp.constraints)
    best = TimeTable(
        selected=[{"code": c, "name": COURSES[c]["name"]} for c in chosen],
        credits=credits_of(chosen),
        notes="גרסה גרידית; נשפר בהמשך"
    )
    alt_chosen, _ = schedule_greedy(list(reversed(base)), inp.constraints)
    alts = []
    if alt_chosen != chosen:
        alts.append(TimeTable(
            selected=[{"code": c, "name": COURSES[c]["name"]} for c in alt_chosen],
            credits=credits_of(alt_chosen),
            notes="אלטרנטיבה הפוכה"
        ))
    return {"timetable": best, "alternatives": alts}

@app.post("/tools/createCalendarEvents")
def create_calendar_events(inp: CalendarIn):
    return {"provider": inp.provider, "event_ids": [f"evt_mock_001"], "status": "mock_created"}

@app.post("/tools/setReminder")
def set_reminder(inp: ReminderIn):
    return {"reminder_id": "rem_mock_001", "topic": inp.topic, "when": inp.when, "status": "scheduled(mock)"}
