#src/utils/state.py
from dataclasses import dataclass, field
import time

@dataclass
class AgentState:
    url: str
    task: str
    framework: str = "playwright"
    tech_info: dict = field(default_factory=dict)  # Detailed tech stack information
    api_endpoints: list = field(default_factory=list)  # Detected API endpoints
    attempt_history: list = field(default_factory=list)
    start: float = field(default_factory=time.time)