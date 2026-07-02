from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import Analysis


@dataclass
class AlertRule:
    name: str
    score_threshold: float
    target_groups: list[str]
    cooldown_sec: int = 1800
    score_filter_enabled: bool = False  # 預設關閉，所有貼文都推送

    def matches(self, analysis: Analysis) -> bool:
        if analysis.sentiment.value == "error":
            return False
        if not self.score_filter_enabled:
            return True
        return analysis.impact_score >= self.score_threshold

    def priority(self) -> int:
        return int(self.score_threshold)

    # Flood-control key used in Redis
    def flood_key(self, analysis: Analysis) -> str:
        author = analysis.post.author_id
        return f"flood:{self.name}:{author}"
