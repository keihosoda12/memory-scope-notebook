"""評価シナリオと提案ロジックの簡易テスト。

使い方: python test_memory_logic.py
Streamlitなしで実行できる（コアロジックのみを検証する）。
"""

from memory_logic import (
    SCOPE_LONG_TERM,
    SCOPE_TODAY_ONLY,
    classify_utterance,
    propose_dinner,
    run_evaluation,
)


def main() -> None:
    passed, total, failures = run_evaluation()
    print(f"classification: {passed}/{total}")
    for failure in failures:
        print(failure)
    assert not failures, "classification scenarios failed"

    approved = [
        classify_utterance("しそが苦手で絶対に食べられない"),
        classify_utterance("チョコレートが大好きで、いつも甘いものを選ぶ"),
        classify_utterance("今日は胃が疲れているから軽めのものがいい"),
    ]
    assert all(c.scope in (SCOPE_LONG_TERM, SCOPE_TODAY_ONLY) for c in approved)

    proposals = propose_dinner(approved)
    names = [p["name"] for p in proposals]
    print("proposals:", names)
    assert "しそ入り和風パスタ" not in names, "disliked dish must be excluded"
    assert any(p["reasons"] for p in proposals), "proposals must cite used memories"
    print("OK")


if __name__ == "__main__":
    main()
