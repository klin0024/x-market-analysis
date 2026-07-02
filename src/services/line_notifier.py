from __future__ import annotations

import logging

import requests

from ..models.analysis import Analysis

logger = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


class LineNotifier:
    def __init__(self, channel_access_token: str, group_ids: dict[str, str]) -> None:
        self._token = channel_access_token
        self.group_ids = group_ids   # label → LINE group ID
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        })

    def push(self, group_id: str, text: str) -> bool:
        payload = {
            "to": group_id,
            "messages": [{"type": "text", "text": text}],
        }
        return self._post(payload)

    def push_flex(self, group_id: str, analysis: Analysis) -> bool:
        payload = {
            "to": group_id,
            "messages": [analysis.to_line_flex_message()],
        }
        return self._post(payload)

    def _post(self, payload: dict) -> bool:
        try:
            resp = self._session.post(LINE_PUSH_URL, json=payload, timeout=10)
            if resp.status_code != 200:
                logger.error("LINE API error %s: %s", resp.status_code, resp.text)
                return False
            return True
        except Exception:
            logger.exception("LINE push failed")
            return False
