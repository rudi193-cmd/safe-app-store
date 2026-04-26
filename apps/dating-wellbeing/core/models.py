from pydantic import BaseModel
from typing import Literal, Optional, List

class Profile(BaseModel):
    raw_text: str
    photos: List[str] = []
    age: Optional[int] = None
    location: Optional[str] = None
    relationship_goal: Optional[str] = None
    bio: str = ""

class IntakeAnswers(BaseModel):
    relation_to_person: Literal["stranger","acquaintance","ex","coworker","hurt_me"]
    why_now: str
    emotional_state: str
    relationship_work_done: str

class AnalysisResult(BaseModel):
    score: int
    category: Literal["incompatible","surface","good_enough","strong","exceptional"]
    depth_vs_fantasy: Literal["depth","fantasy","mixed"]
    red_flags: List[str] = []
    yellow_flags: List[str] = []
    intervention_level: Literal["none","yellow","red","danger"]
    recommendation: str
    reflection_questions: List[str]
    confidence: float
