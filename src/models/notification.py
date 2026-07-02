from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from .analysis import Analysis


@dataclass
class Notification:
    analysis: Analysis
    group_id: str
    status: str = "pending"          # pending / sent / failed / skipped
    sent_at: datetime | None = None
    notif_id: str = field(default_factory=lambda: str(uuid.uuid4()))
