"""AIメモリ手帳のコアロジック（UI非依存・決定的に動く）

会話の発話を「ずっと覚える / 今日だけ / 要確認 / 捨てる」の4つの
scope（記憶の範囲）に分類し、承認済みメモリだけを使って夕食候補を提案する。
外部LLM APIは使わず、キーワードとルールで判定するため再現性がある。
"""

from dataclasses import dataclass, field

SCOPE_LONG_TERM = "long_term"    # ずっと覚える
SCOPE_TODAY_ONLY = "today_only"  # 今日だけ
SCOPE_NEEDS_CHECK = "needs_check"  # 要確認
SCOPE_DISCARD = "discard"        # 捨てる

SCOPE_LABELS = {
    SCOPE_LONG_TERM: "ずっと覚える",
    SCOPE_TODAY_ONLY: "今日だけ",
    SCOPE_NEEDS_CHECK: "要確認",
    SCOPE_DISCARD: "捨てる",
}

# --- 分類ルール -----------------------------------------------------------

# 一時的な状態を示すマーカー（今日だけ）
TEMPORAL_MARKERS = ["今日は", "今夜は", "今回は", "今は", "今日だけ", "このあと"]
# 恒常的な好み・制約を示すマーカー（ずっと覚える）
STABLE_MARKERS = ["いつも", "大好き", "苦手", "アレルギー", "絶対に", "必ず"]
# 断定できない言い方（要確認）
HEDGE_MARKERS = ["かもしれない", "たぶん", "気がする", "っぽい", "かも"]
# 単なる依頼・作業指示（捨てる）
REQUEST_MARKERS = ["買ってきて", "教えて", "予約して", "調べて", "開いて"]


@dataclass
class MemoryCandidate:
    text: str
    scope: str
    confidence: float
    reason: str


def classify_utterance(text: str) -> MemoryCandidate:
    """発話1件を scope に分類する。優先順位: 依頼 > 一時 > 推量 > 恒常。"""
    # 1. 純粋な依頼文は、好みの情報が含まれていなければ捨てる
    if any(m in text for m in REQUEST_MARKERS) and not any(
        m in text for m in STABLE_MARKERS + TEMPORAL_MARKERS
    ):
        return MemoryCandidate(text, SCOPE_DISCARD, 0.9, "単なる依頼・作業指示のため")

    # 2. 一時マーカーがあれば「今日だけ」
    hit = [m for m in TEMPORAL_MARKERS if m in text]
    if hit:
        return MemoryCandidate(
            text, SCOPE_TODAY_ONLY, 0.85, f"一時的な状態の表現（{hit[0]}）を含むため"
        )

    # 3. 推量表現があれば断定せず「要確認」
    hit = [m for m in HEDGE_MARKERS if m in text]
    if hit:
        return MemoryCandidate(
            text, SCOPE_NEEDS_CHECK, 0.5, f"断定できない言い方（{hit[0]}）を含むため"
        )

    # 4. 恒常マーカーがあれば「ずっと覚える」
    hit = [m for m in STABLE_MARKERS if m in text]
    if hit:
        return MemoryCandidate(
            text, SCOPE_LONG_TERM, 0.9, f"恒常的な好み・制約の表現（{hit[0]}）を含むため"
        )

    # 5. どれにも当てはまらなければ、勝手に覚えず「要確認」
    return MemoryCandidate(text, SCOPE_NEEDS_CHECK, 0.4, "判定材料が弱いため確認が必要")


# --- 提案ロジック ---------------------------------------------------------

@dataclass
class Dish:
    name: str
    tags: set = field(default_factory=set)


DINNER_CATALOG = [
    Dish("白身魚のムニエル", {"魚", "軽め", "あっさり"}),
    Dish("鶏むね肉のサラダプレート", {"肉", "軽め", "あっさり"}),
    Dish("濃厚チョコレートケーキ（デザート）", {"甘い", "チョコ"}),
    Dish("しそ入り和風パスタ", {"しそ", "軽め"}),
    Dish("麻婆豆腐", {"辛い", "重め"}),
    Dish("牛すき焼き", {"肉", "重め", "甘い"}),
    Dish("海鮮丼", {"魚", "あっさり"}),
    Dish("クリームシチュー", {"重め", "あっさり"}),
]

# メモリ文から拾うキーワード → 対象タグ。
# 好き/苦手のどちらの意味で使われたかは、メモリ文全体の肯定/否定で判定する。
KEYWORD_TAGS = {
    "しそ": "しそ",
    "辛い": "辛い",
    "チョコ": "チョコ",
    "甘い": "甘い",
    "魚": "魚",
}
NEGATIVE_MARKERS = ["苦手", "食べられない", "避け", "ダメ", "無理"]


def propose_dinner(approved: list[MemoryCandidate], top_n: int = 3) -> list[dict]:
    """承認済みメモリ（long_term / today_only）だけを使って候補を返す。

    各候補には「どのメモリを使ったか」を理由として必ず付ける。
    """
    usable = [m for m in approved if m.scope in (SCOPE_LONG_TERM, SCOPE_TODAY_ONLY)]
    excluded_tags: set = set()
    liked_tags: set = set()
    used_by_tag: dict[str, list[str]] = {}

    for mem in usable:
        negative = any(m in mem.text for m in NEGATIVE_MARKERS)
        for keyword, tag in KEYWORD_TAGS.items():
            if keyword not in mem.text:
                continue
            if negative:
                excluded_tags.add(tag)
            else:
                liked_tags.add(tag)
            used_by_tag.setdefault(tag, []).append(mem.text)
        # 「軽め」は避けたい対象ではなく希望として扱う
        if "軽め" in mem.text:
            liked_tags.add("軽め")
            used_by_tag.setdefault("軽め", []).append(mem.text)

    scored: list[dict] = []
    for dish in DINNER_CATALOG:
        if dish.tags & excluded_tags:
            continue
        matched = dish.tags & liked_tags
        reasons = []
        for tag in sorted(matched):
            for src in used_by_tag.get(tag, []):
                reasons.append(f"「{src}」というメモリを使いました")
        scored.append(
            {"name": dish.name, "score": len(matched), "reasons": reasons}
        )

    scored.sort(key=lambda d: (-d["score"], d["name"]))
    return scored[:top_n]


# --- 評価シナリオ ----------------------------------------------------------

EVALUATION_SCENARIOS = [
    ("チョコレートが大好きで、いつも甘いものを選ぶ", SCOPE_LONG_TERM),
    ("しそが苦手で絶対に食べられない", SCOPE_LONG_TERM),
    ("今日は胃が疲れているから軽めのものがいい", SCOPE_TODAY_ONLY),
    ("今夜は時間がないので簡単に済ませたい", SCOPE_TODAY_ONLY),
    ("辛いものも好きかもしれないけど自信がない", SCOPE_NEEDS_CHECK),
    ("たぶん魚より肉派な気がする", SCOPE_NEEDS_CHECK),
    ("牛乳を買ってきて", SCOPE_DISCARD),
    ("明日の予定を教えて", SCOPE_DISCARD),
]


def run_evaluation() -> tuple[int, int, list[str]]:
    """評価シナリオを実行し、(正解数, 全件数, 失敗詳細) を返す。"""
    failures: list[str] = []
    for text, expected in EVALUATION_SCENARIOS:
        got = classify_utterance(text)
        if got.scope != expected:
            failures.append(f"NG: 「{text}」 expected={expected} got={got.scope}")
    total = len(EVALUATION_SCENARIOS)
    return total - len(failures), total, failures
