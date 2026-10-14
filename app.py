from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

import streamlit as st

from mahjong_analyzer.analytics import ContextFilters, DIMENSIONS, SCORE_TARGETS, parse_score_bins
from mahjong_analyzer.dashboard.data import (
    candidate_data,
    connect_readonly,
    context_data,
    home_data,
    scene_data,
)
from mahjong_analyzer.errors import AnalyzerError


DIMENSION_LABELS = {
    "all": "全体", "turn_phase": "巡目帯", "shanten_group": "向聴数",
    "riichi_group": "他家リーチ人数", "rank": "順位", "score_diff": "点数差",
    "action_category": "行動種類", "bakaze": "場風", "dealer": "親・子",
    "kyoku": "局番号", "honba": "本場",
}


def _filters_from_state(values: dict[str, Any] | None = None) -> ContextFilters:
    values = values or {}
    return ContextFilters(
        extractor_version=values.get("extractor_version", "phase2-context-v1"),
        turn_min=values.get("turn_min"), turn_max=values.get("turn_max"),
        turn_phase=values.get("turn_phase"), shanten=values.get("shanten"),
        shanten_group=values.get("shanten_group"), riichi_count=values.get("riichi_count"),
        riichi_min=values.get("riichi_min"), riichi_max=values.get("riichi_max"),
        rank=values.get("rank"), rank_unknown=values.get("rank_unknown", False),
        score_target=values.get("score_target"), score_min=values.get("score_min"),
        score_max=values.get("score_max"), action_category=values.get("action_category"),
        bakaze=values.get("bakaze"), kyoku=values.get("kyoku"), honba=values.get("honba"),
        is_dealer=values.get("is_dealer"), model_tag=values.get("model_tag"),
        reviewer_version=values.get("reviewer_version"), temperature=values.get("temperature"),
        is_equal=values.get("is_equal"), probability_min=values.get("probability_min"),
        probability_max=values.get("probability_max"),
    )


def _filter_controls(prefix: str, initial: ContextFilters = ContextFilters()) -> ContextFilters:
    phases = [None, "early", "mid", "late", "unknown"]
    groups = [None, "tenpai", "one", "two", "three_plus", "negative", "unknown"]
    actions = [None, "discard", "riichi", "chi", "pon", "ankan", "kakan", "daiminkan", "hora", "none"]
    phase = st.selectbox("巡目区分", phases, index=phases.index(initial.turn_phase), key=f"{prefix}-phase")
    shanten_group = st.selectbox("向聴数区分", groups, index=groups.index(initial.shanten_group), key=f"{prefix}-shanten")
    riichi = st.number_input("他家リーチ人数（指定なしは-1）", min_value=-1, max_value=4,
                             value=-1 if initial.riichi_count is None else initial.riichi_count,
                             key=f"{prefix}-riichi")
    action = st.selectbox("行動種類", actions, index=actions.index(initial.action_category), key=f"{prefix}-action")
    score_target = st.selectbox("点数差の対象", [None, *SCORE_TARGETS],
                                index=([None, *SCORE_TARGETS]).index(initial.score_target),
                                key=f"{prefix}-score-target")
    col1, col2 = st.columns(2)
    with col1:
        score_min = st.number_input("点数差 最小（指定なしは空欄扱い）", value=initial.score_min or 0,
                                    key=f"{prefix}-score-min")
    with col2:
        score_max = st.number_input("点数差 最大（指定なしは空欄扱い）", value=initial.score_max or 0,
                                    key=f"{prefix}-score-max")
    use_score_range = st.checkbox("点数差の範囲を使う", value=initial.score_min is not None or initial.score_max is not None,
                                  key=f"{prefix}-use-score")
    return ContextFilters(
        extractor_version=initial.extractor_version,
        turn_phase=phase, shanten_group=shanten_group,
        riichi_count=None if riichi < 0 else riichi,
        action_category=action, score_target=score_target,
        score_min=score_min if use_score_range else None,
        score_max=score_max if use_score_range else None,
        model_tag=initial.model_tag, reviewer_version=initial.reviewer_version,
    )


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "decisions": sum(row["decision_count"] for row in rows),
        "agreement_numerator": sum(row["agreement_numerator"] for row in rows),
        "agreement_denominator": sum(row["agreement_denominator"] for row in rows),
        "low_numerator": sum(row["low_probability_numerator"] for row in rows),
        "low_denominator": sum(row["low_probability_denominator"] for row in rows),
    }


def _rate(numerator: int, denominator: int) -> str:
    return "該当データなし" if denominator == 0 else f"{numerator / denominator:.1%} ({numerator}/{denominator})"


def _home(connection: Any) -> None:
    st.title("Mahjong Analyzer")
    data = home_data(connection)
    rows = []
    for item in data["summaries"]:
        rows.append(item)
    decisions = sum(item["total_reviewed"] for item in rows)
    matches = sum(item["total_matches"] for item in rows)
    comparable = sum(item["comparable_decisions"] for item in rows)
    low = sum(item["low_probability_decisions"] for item in rows)
    cols = st.columns(5)
    cols[0].metric("解析済み半荘", data["games"])
    cols[1].metric("対象判断", decisions)
    cols[2].metric("AI一致率", _rate(matches, decisions))
    cols[3].metric("低推奨選択率", _rate(low, comparable))
    cols[4].metric("AI不一致", decisions - matches)
    st.caption("低推奨選択率は客観的な悪手率ではありません。Mortal Ratingはレビュー単位で表示します。")
    st.subheader("評価条件別の指標")
    st.dataframe([{
        "engine": item["condition"]["engine"], "reviewer": item["condition"]["reviewer_version"],
        "model": item["condition"]["model_tag"], "判断数": item["total_reviewed"],
        "AI一致": f"{item['total_matches']}/{item['total_reviewed']}",
        "低推奨": f"{item['low_probability_decisions']}/{item['comparable_decisions']}",
        "Mortal Rating": item["ratings"],
    } for item in rows], use_container_width=True, hide_index=True)
    st.subheader("最近の対局")
    st.dataframe(data["recent_games"], use_container_width=True, hide_index=True)


def _analysis(connection: Any) -> None:
    st.title("状況別分析")
    dimension = st.selectbox("分析軸", DIMENSIONS, format_func=lambda x: DIMENSION_LABELS[x])
    filters = _filter_controls("analysis", _filters_from_state(st.session_state.get("analysis_filters")))
    score_target = filters.score_target if dimension == "score_diff" else None
    bins_text = st.text_input("点数差区間（0から始まるカンマ区切り）", "0,4000,8000,12000")
    try:
        bins = parse_score_bins(bins_text)
        rows = context_data(connection, dimension=dimension, filters=filters, score_target=score_target, score_bins=bins)
    except (AnalyzerError, ValueError) as exc:
        st.error(str(exc))
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if rows:
        st.bar_chart({"判断数": {row["group"]: row["decision_count"] for row in rows}})
    if st.button("この条件で復習候補へ"):
        st.session_state["candidate_filters"] = asdict(filters)
        st.session_state["navigation_target"] = "candidates"
        st.rerun()


def _candidates(connection: Any) -> None:
    st.title("復習候補")
    initial = _filters_from_state(st.session_state.get("candidate_filters"))
    sort = st.selectbox("並び順", ["low-probability", "disagreement", "recent"], key="candidate-sort")
    disagreement_only = st.checkbox("AI不一致だけ", key="candidate-disagreement")
    filters = _filter_controls("candidate", initial)
    limit = st.number_input("1ページ件数", min_value=1, max_value=500, value=20, key="candidate-limit")
    offset = st.number_input("開始位置", min_value=0, value=0, step=1, key="candidate-offset")
    try:
        result = candidate_data(connection, sort=sort, filters=filters,
                                disagreement_only=disagreement_only, offset=offset, limit=limit)
    except (AnalyzerError, ValueError) as exc:
        st.error(str(exc))
        return
    st.write(f"該当 {result.total} 件 / 表示 {len(result.items)} 件")
    st.dataframe(list(result.items), use_container_width=True, hide_index=True)
    ids = [item["decision_id"] for item in result.items]
    if ids:
        selected = st.selectbox("詳細を表示するdecision_id", ids)
        if st.button("局面詳細を開く"):
            st.session_state["selected_decision_id"] = selected
            st.session_state["navigation_target"] = "decision"
            st.rerun()


def _decision(connection: Any, review_root: Path, source_root: Path) -> None:
    st.title("局面詳細")
    default_id = st.session_state.get("selected_decision_id", 1)
    decision_id = st.number_input("decision_id", min_value=1, value=default_id, step=1)
    if st.button("局面を読み込む") or decision_id == default_id:
        try:
            scene = scene_data(connection, decision_id, review_root=review_root, source_root=source_root)
        except (AnalyzerError, OSError, ValueError) as exc:
            st.error(str(exc))
            return
        st.success(f"復元状態: {scene['status']}")
        st.json({"identity": scene["identity"], "round": scene["round"], "score": scene["score"]})
        st.subheader("手牌・副露")
        st.write("手牌:", " ".join(scene["hand"]["tiles"] or []))
        st.write("ツモ牌:", scene["hand"]["tsumo_tile"])
        st.json({"fuuros": scene["hand"]["fuuros"], "shanten": scene["hand"]["shanten"],
                 "self_riichi": scene["hand"]["self_riichi"]})
        st.subheader("公開情報")
        st.json(scene["public"])
        st.subheader("Mortal評価")
        st.json(scene["mortal"])
        st.caption("Mortalの確率・Q値は評価情報であり、期待失点ではありません。")
    if st.button("候補一覧へ戻る"):
        st.session_state["navigation_target"] = "candidates"
        st.rerun()


def main() -> None:
    st.set_page_config(page_title="Mahjong Analyzer", layout="wide")
    st.sidebar.title("Mahjong Analyzer")
    database = Path(st.sidebar.text_input("SQLite", "local_data/mahjong_analyzer.sqlite3"))
    review_root = Path(st.sidebar.text_input("レビューJSONルート", "local_data"))
    source_root = Path(st.sidebar.text_input("元牌譜ルート", "data/raw/tenhou"))
    navigation_target = st.session_state.pop("navigation_target", None)
    if navigation_target in {"home", "analysis", "candidates", "decision"}:
        st.session_state["page_selector"] = navigation_target
    current_page = st.session_state.get("page_selector", "home")
    page = st.sidebar.radio("画面", ["home", "analysis", "candidates", "decision"],
                            format_func={"home": "ホーム", "analysis": "状況別分析",
                                         "candidates": "復習候補", "decision": "局面詳細"}.get,
                            key="page_selector", index=["home", "analysis", "candidates", "decision"].index(
                                current_page))
    try:
        connection = connect_readonly(database)
    except (OSError, sqlite3.Error) as exc:
        st.error(f"SQLiteを読み込めません。パスとファイルの存在を確認してください: {exc}")
        st.stop()
    try:
        if page == "home":
            _home(connection)
        elif page == "analysis":
            _analysis(connection)
        elif page == "candidates":
            _candidates(connection)
        else:
            _decision(connection, review_root, source_root)
    finally:
        connection.close()


if __name__ == "__main__":
    main()
