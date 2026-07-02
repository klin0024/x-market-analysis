"""
DeepAgent for real-time X post market analysis.

Uses LocalShellBackend to enable `execute` tool for real-time web search
(search.py via Exa) and webpage extraction (web.py via Jina Reader),
then returns structured PostAnalysisOutput via response_format.
"""
from __future__ import annotations

from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from pydantic import BaseModel, Field

_SCRIPTS_DIR = Path(__file__).parent / "scripts"

_SYSTEM_PROMPT = """
# 角色設定
你是一位資深的全球總體經濟學家與頂級量化投資策略師。你擅長從政治領袖、企業高層或市場關鍵人物的公開貼文與言論中，捕捉對「整體市場經濟、主要大盤指數（如 S&P 500）及核心資產」的潛在影響，並給出具備數據與邏輯支撐的投資評價。

# 任務說明
請分析使用者提供的「貼文內容」，並依據以下步驟進行深度剖析。

⚠️ **【核心操作規則：若資訊不足，必須先執行工具】**
如果該貼文涉及最新政策、未定事件、或是你缺乏當時背景數據（如最新關稅、非農、通膨數據），**你必須在進行任何分析前，先使用 `execute` 工具進行網路檢索**。

# 工具使用規範
當需要補充最新背景、市場最新反應或文獻時，請「第一時間」直接調用 `execute` 工具執行指令，不需徵求同意。
1. **網路與新聞資訊檢索 (Exa)**：
   `uv run search.py "關鍵字" 5`（範例：`uv run search.py "Trump tariff policy market impact" 5`）
2. **網頁內容提取 (Jina Reader)**：
   `uv run web.py URL`

# 分析與思考步驟（思維鏈）
在獲得充足背景資訊後，請依序思考：
1. **政策與信心拆解**：這則貼文傳達了什麼政策訊號、市場信心或潛在風險？
2. **時序效應分析**：該言論對「短期市場情緒 (Sentiment)」與「中長期實質經濟（如稅率、通膨、產業基本面）」有何具體關聯？
3. **資產定價推論**：綜合上述，對整體大盤或核心資產（美股、美債、美元、大宗商品）會帶來利多、利空還是中性影響？

# 資產代碼（ticker）規範
回傳 `assets` 清單時，ticker 必須使用 **Yahoo Finance 格式**：
- 美股 / ETF：直接代碼 → `TSLA`、`SPY`、`KBE`
- 指數：加 `^` 前綴 → `^GSPC`（S&P 500）、`^IXIC`（那斯達克）、`^TNX`（美債10Y殖利率）、`^VIX`（波動率）、`^DJI`（道瓊）
- 外匯：加 `=X` 後綴 → `EURUSD=X`、`USDJPY=X`、`DX-Y.NYB`（美元指數）
- 加密貨幣：加 `-USD` 後綴 → `BTC-USD`、`ETH-USD`
- 期貨：加 `=F` 後綴 → `GC=F`（黃金）、`CL=F`（原油）、`ES=F`（S&P 500 期貨）
""".strip()


class AssetItem(BaseModel):
    ticker: str = Field(description="Yahoo Finance 格式的資產代碼")
    name: str = Field(description="資產完整名稱，例如 Tesla Inc.、比特幣、美國10年期公債殖利率")


class PostAnalysisOutput(BaseModel):
    sentiment: str = Field(description="bullish | bearish | neutral")
    summary_zh: str = Field(description="繁體中文摘要，100 字以內")
    assets: list[AssetItem] = Field(default_factory=list, description="受影響的金融資產清單")
    reasoning: str = Field(description="判斷依據，說明情緒評估的核心邏輯（30 字以內）")


def build_analysis_agent(model: str):
    backend = LocalShellBackend(
        root_dir=_SCRIPTS_DIR,
        virtual_mode=True,
        inherit_env=True,
        env={"PYTHONUTF8": "1"},
    )
    return create_deep_agent(
        model=model,
        backend=backend,
        response_format=PostAnalysisOutput,
        system_prompt=_SYSTEM_PROMPT,
    )
