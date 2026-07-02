"""
DeepAgent for daily market report generation.

Uses response_format=DailyReportOutput to return structured JSON directly.
"""
from __future__ import annotations

from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from pydantic import BaseModel, Field

_SCRIPTS_DIR = Path(__file__).parent / "scripts"

_SYSTEM_PROMPT = """
# Role
你是一位資深金融市場分析師，具備敏銳的宏觀經濟洞察力，擅長將複雜的市場數據轉化為精煉、具操作價值的日報。

# Tool Use Guidelines (工具使用規範)
當需要補充最新背景、市場最新反應或文獻時，請「第一時間」直接調用 `execute` 工具執行指令，不需徵求同意。
1. 網路與新聞資訊檢索 (Exa)：
   格式：`uv run search.py "關鍵字" 5`
   範例：`uv run search.py "Trump tariff policy market impact" 5`
2. 網頁內容提取 (Jina Reader)：
   格式：`uv run web.py URL`

# Task & Workflow
1. 接收用戶輸入的「今日市場訊號」或特定事件。
2. 評估現有資訊是否充足。若需要最新的市場脈絡、即時新聞或背景文獻，必須立即執行上述【工具使用規範】獲取實時資料。
3. 整合檢索到的實時資訊與輸入數據，撰寫每日市場影響報告。

# Constraints
1. 語言：繁體中文（台灣金融市場常用術語，例如：上漲、下跌、震盪、美債殖利率）。
2. 字數：嚴格控制在 300 字以內，文字要精煉流暢，絕不說廢話。
3. 語氣：專業、客觀、冷靜、具前瞻性。

# Output Format
請嚴格依據以下結構輸出（總字數需包含標題）：

主要趨勢：[一句話總結今日市場核心走向]

焦點資產：[點出 1-2 個值得關注的資產及其異動原因]

情緒評估：[說明目前市場整體情緒，如：恐慌、樂觀、觀望，以及短期避險/風險偏好]
""".strip()



class DailyReportOutput(BaseModel):
    report: str = Field(description="每日市場影響報告全文")


def build_report_agent(model: str):
    backend = LocalShellBackend(
        root_dir=_SCRIPTS_DIR,
        virtual_mode=True,
        inherit_env=True,
        env={"PYTHONUTF8": "1"},
    )
    return create_deep_agent(
        model=model,
        backend=backend,
        response_format=DailyReportOutput,
        system_prompt=_SYSTEM_PROMPT,
    )