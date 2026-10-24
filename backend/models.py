"""Pydantic request models. Times inside the API are 24-hour "HH:MM" / ISO strings;
the frontend turns every one of them into 12-hour AM/PM before a person sees it."""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

HM = r"^([01]\d|2[0-3]):[0-5]\d$"
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class SettingsIn(BaseModel):
    nickname: Optional[str] = Field(None, max_length=40)
    timezone: str = "America/New_York"
    sleep_goal_min: int = Field(510, ge=300, le=720)
    wake_times: Dict[str, str]
    school_blocks: Dict[str, Optional[List[str]]]
    commute_min: int = Field(20, ge=0, le=180)
    max_study_school_night_min: int = Field(120, ge=15, le=600)
    max_study_weekend_day_min: int = Field(240, ge=15, le=720)

    @field_validator("wake_times")
    @classmethod
    def _wake(cls, v):
        import re
        for k in DAY_KEYS:
            if k not in v or not re.match(HM, v[k]):
                raise ValueError(f"wake time for {k} must be HH:MM")
        return {k: v[k] for k in DAY_KEYS}

    @field_validator("school_blocks")
    @classmethod
    def _school(cls, v):
        import re
        out = {}
        for k in DAY_KEYS:
            b = v.get(k)
            if b:
                if len(b) != 2 or not all(re.match(HM, x) for x in b) or b[0] >= b[1]:
                    raise ValueError(f"school hours for {k} must be [start, end]")
            out[k] = b or None
        return out


class Recurring(BaseModel):
    days: List[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]]


class EventIn(BaseModel):
    kind: Literal["shift", "activity"]
    title: str = Field(..., min_length=1, max_length=80)
    start: str
    end: str
    recurring: Optional[Recurring] = None


class EventPatch(BaseModel):
    kind: Optional[Literal["shift", "activity"]] = None
    title: Optional[str] = Field(None, min_length=1, max_length=80)
    start: Optional[str] = None
    end: Optional[str] = None
    recurring: Optional[Recurring] = None


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subject: str = Field(..., min_length=1, max_length=40)
    task_type: Literal["homework", "essay", "test_study", "project"] = "homework"
    due: str
    guess_min: int = Field(..., ge=5, le=2400)
    planned_min: Optional[int] = Field(None, ge=5, le=4800)


class TaskPatch(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=120)
    subject: Optional[str] = None
    task_type: Optional[Literal["homework", "essay", "test_study", "project"]] = None
    due: Optional[str] = None
    guess_min: Optional[int] = Field(None, ge=5, le=2400)
    planned_min: Optional[int] = Field(None, ge=5, le=4800)
    done_min: Optional[int] = Field(None, ge=0)


class MinutesIn(BaseModel):
    minutes: int = Field(0, ge=0, le=1440)


class CheckinIn(BaseModel):
    date: Optional[str] = None
    sleep_min: Optional[int] = Field(None, ge=0, le=1440)
    energy: Optional[int] = Field(None, ge=1, le=5)
    stress: Optional[int] = Field(None, ge=1, le=5)


class CameUpIn(BaseModel):
    start: Optional[str] = None
    minutes: Optional[int] = Field(None, ge=1, le=14 * 1440)
    rest_of_today: bool = False


class TextIn(BaseModel):
    text: str = Field("", max_length=2000)


class DecisionCoachIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=600)
    option_a: Optional[str] = Field(None, max_length=120)
    option_b: Optional[str] = Field(None, max_length=120)
    event: Optional[EventIn] = None


class CalendarEventIn(BaseModel):
    title: str = Field("Busy", max_length=120)
    start: str
    end: str


class CalendarImportIn(BaseModel):
    """Events the browser read from Google Calendar. They replace any earlier import."""
    events: List[CalendarEventIn] = Field(default_factory=list, max_length=300)


class GoogleTaskImportItem(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=300)
    title: str = Field(..., min_length=1, max_length=120)
    subject: str = Field(..., min_length=1, max_length=40)
    due: str
    guess_min: int = Field(..., ge=5, le=2400)
    task_type: Literal["homework", "essay", "test_study", "project"] = "homework"


class GoogleTasksImportIn(BaseModel):
    tasks: List[GoogleTaskImportItem] = Field(default_factory=list, max_length=300)


class GoogleTaskSuggestItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    list_title: str = Field("", max_length=120)


class GoogleTaskSuggestIn(BaseModel):
    tasks: List[GoogleTaskSuggestItem] = Field(default_factory=list, max_length=40)
    use_ai: bool = True


class GoogleIn(BaseModel):
    credential: str = Field(..., min_length=20, max_length=4096)


class AuthIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=40)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def _clean(cls, v):
        return v.strip().lower().lstrip("@")
