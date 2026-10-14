from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import streamlit as st

from mahjong_analyzer.analytics import ContextFilters, DIMENSIONS, SCORE_TARGETS, parse_score_bins
from mahjong_analyzer.dashboard.data import (
    DashboardPaths, candidate_data, connect_readonly, context_data, home_data,
    load_dashboard_paths, scene_data,
)
from mahjong_analyzer.errors import AnalyzerError
from mahjong_analyzer.review import adjacent_decisions
from mahjong_analyzer.table_view import compact_table_data, tile_ids_from_action
from mahjong_analyzer.tile_assets import tile_asset
from mahjong_analyzer.dashboard.table_renderer import render_evaluation_html, render_table_html, table_css


DIMENSION_LABELS = {
    "all": "全体", "turn_phase": "巡目帯", "shanten_group": "向聴数",
    "riichi_group": "他家リーチ人数", "rank": "順位", "score_diff": "点数差",
    "action_category": "行動種類", "bakaze": "場風", "dealer": "親・子",
    "kyoku": "局番号", "honba": "本場",
}
PHASE_LABELS = {None: "すべて", "early": "序盤（1〜6巡）", "mid": "中盤（7〜12巡）",
                "late": "終盤（13巡以降）", "unknown": "不明"}
SHANTEN_LABELS = {None: "すべて", "tenpai": "聴牌", "one": "1向聴", "two": "2向聴",
                  "three_plus": "3向聴以上", "negative": "和了形等（負値）", "unknown": "不明"}
ACTION_LABELS = {None: "すべて", "discard": "通常打牌", "riichi": "リーチ判断", "chi": "チー",
                 "pon": "ポン", "ankan": "暗槓", "kakan": "加槓", "daiminkan": "大明槓",
                 "hora": "和了", "none": "非行動判断", "unknown": "不明"}
RIICHI_LABELS = {None: "すべて", 0: "なし", 1: "1人", 2: "2人以上"}
SCORE_TARGET_LABELS = {None: "指定なし", "top": "トップとの差", "last": "ラスとの差",
                       "above": "直上との差", "below": "直下との差"}
SORT_LABELS = {"low-probability": "推奨確率が低い順", "disagreement": "AI不一致を優先",
               "recent": "新しい対局順"}
GRAPH_LABELS = {"decision_count": "判断数", "ai_agreement_rate": "AI一致率",
                "low_recommendation_rate": "低推奨選択率"}


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
        model_identity=values.get("model_identity"), grp_identity=values.get("grp_identity"),
        reviewer_version=values.get("reviewer_version"), temperature=values.get("temperature"),
        rule_context=values.get("rule_context"), is_equal=values.get("is_equal"),
        probability_min=values.get("probability_min"), probability_max=values.get("probability_max"),
    )


def _rate(numerator: int, denominator: int) -> str:
    return "該当データなし" if denominator == 0 else f"{numerator / denominator:.1%} ({numerator}/{denominator})"


def _condition_key(condition: dict[str, Any]) -> str:
    return json.dumps(condition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _condition_label(condition: dict[str, Any]) -> str:
    model = condition.get("model_tag") or "モデル不明"
    reviewer = condition.get("reviewer_version") or "reviewer不明"
    temperature = condition.get("temperature")
    rule = "標準ルール情報なし" if condition.get("rule_context") is None else "ルール情報あり"
    return f"{model} / reviewer {reviewer} / 温度 {temperature} / {rule}"


def _condition_options(summaries: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    conditions = {}
    for item in summaries:
        condition = item["condition"]
        conditions[_condition_key(condition)] = condition
    keys = sorted(conditions)
    return keys, conditions


def _select_condition(prefix: str, summaries: list[dict[str, Any]], initial: ContextFilters) -> ContextFilters:
    keys, conditions = _condition_options(summaries)
    if not keys:
        st.warning("評価条件が登録されたレビューはありません。")
        return initial
    initial_key = _condition_key({
        "engine": "Mortal", "reviewer_version": initial.reviewer_version,
        "model_tag": initial.model_tag, "model_identity": initial.model_identity, "grp_identity": initial.grp_identity,
        "temperature": initial.temperature, "rule_context": None if initial.rule_context == "" else initial.rule_context,
    })
    selected_key = initial_key if initial_key in conditions else keys[0]
    selected_key = st.selectbox(
        "評価条件（同じモデル・温度・ルールのみ集計）", keys,
        index=keys.index(selected_key), format_func=lambda key: _condition_label(conditions[key]),
        key=f"{prefix}-condition",
    )
    condition = conditions[selected_key]
    return replace(initial, model_tag=condition.get("model_tag"),
                   model_identity=condition.get("model_identity"), grp_identity=condition.get("grp_identity"),
                   reviewer_version=condition.get("reviewer_version"),
                   temperature=condition.get("temperature"),
                   rule_context="" if condition.get("rule_context") is None else condition.get("rule_context"))


def _filter_controls(prefix: str, initial: ContextFilters = ContextFilters()) -> ContextFilters:
    phases = list(PHASE_LABELS)
    groups = list(SHANTEN_LABELS)
    actions = list(ACTION_LABELS)
    col1, col2, col3 = st.columns(3)
    with col1:
        phase = st.selectbox("巡目区分", phases, index=phases.index(initial.turn_phase),
                             format_func=PHASE_LABELS.get, key=f"{prefix}-phase")
    with col2:
        shanten_group = st.selectbox("向聴数区分", groups, index=groups.index(initial.shanten_group),
                                     format_func=SHANTEN_LABELS.get, key=f"{prefix}-shanten")
    with col3:
        riichi = st.selectbox("他家リーチ状況", list(RIICHI_LABELS),
                              index=list(RIICHI_LABELS).index(initial.riichi_count),
                              format_func=RIICHI_LABELS.get, key=f"{prefix}-riichi")
    with st.expander("詳細条件", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            rank = st.selectbox("暫定順位", [None, 1, 2, 3, 4],
                                index=[None, 1, 2, 3, 4].index(initial.rank),
                                format_func=lambda value: "指定なし" if value is None else f"{value}位",
                                key=f"{prefix}-rank")
            rank_unknown = st.checkbox("同点など順位不明を含む", value=initial.rank_unknown,
                                       key=f"{prefix}-rank-unknown")
        with col2:
            score_target = st.selectbox("点数差の比較対象", [None, *SCORE_TARGETS],
                                        index=([None, *SCORE_TARGETS]).index(initial.score_target),
                                        format_func=SCORE_TARGET_LABELS.get, key=f"{prefix}-score-target")
            use_score_range = st.checkbox("点数差の範囲を使う",
                                          value=initial.score_min is not None or initial.score_max is not None,
                                          key=f"{prefix}-use-score")
        with col3:
            action = st.selectbox("行動種類", actions, index=actions.index(initial.action_category),
                                  format_func=ACTION_LABELS.get, key=f"{prefix}-action")
            is_dealer = st.selectbox("親・子", [None, True, False],
                                     index=[None, True, False].index(initial.is_dealer),
                                     format_func=lambda value: "指定なし" if value is None else ("親" if value else "子"),
                                     key=f"{prefix}-dealer")
        col1, col2, col3 = st.columns(3)
        with col1:
            score_min = st.number_input("点数差 最小", value=initial.score_min or 0,
                                        disabled=not use_score_range, key=f"{prefix}-score-min")
        with col2:
            score_max = st.number_input("点数差 最大", value=initial.score_max or 0,
                                        disabled=not use_score_range, key=f"{prefix}-score-max")
        with col3:
            probability_min = st.number_input("本人の推奨確率 最小", min_value=0.0, max_value=1.0,
                                              value=initial.probability_min or 0.0, step=0.01,
                                              key=f"{prefix}-prob-min")
            probability_max = st.number_input("本人の推奨確率 最大", min_value=0.0, max_value=1.0,
                                              value=initial.probability_max or 0.0, step=0.01,
                                              key=f"{prefix}-prob-max")
        use_probability_range = st.checkbox("推奨確率の範囲を使う",
                                            value=initial.probability_min is not None or initial.probability_max is not None,
                                            key=f"{prefix}-use-prob")
        col1, col2, col3 = st.columns(3)
        with col1:
            bakaze = st.selectbox("場風", [None, "E", "S", "W", "N"],
                                  index=[None, "E", "S", "W", "N"].index(initial.bakaze),
                                  format_func=lambda value: "指定なし" if value is None else {"E": "東場", "S": "南場", "W": "西場", "N": "北場"}[value],
                                  key=f"{prefix}-bakaze")
        with col2:
            kyoku = st.number_input("局番号（指定なしは0）", min_value=0, value=initial.kyoku or 0,
                                    key=f"{prefix}-kyoku")
        with col3:
            honba = st.number_input("本場（指定なしは-1）", min_value=-1, value=-1 if initial.honba is None else initial.honba,
                                    key=f"{prefix}-honba")
    return replace(initial, turn_phase=phase, shanten_group=shanten_group,
                   riichi_count=riichi if riichi in (0, 1) else None,
                   riichi_min=2 if riichi == 2 else None, rank=rank, rank_unknown=rank_unknown,
                   action_category=action, is_dealer=is_dealer, bakaze=bakaze,
                   kyoku=None if kyoku == 0 else kyoku, honba=None if honba < 0 else honba,
                   score_target=score_target,
                   score_min=score_min if use_score_range else None,
                   score_max=score_max if use_score_range else None,
                   probability_min=probability_min if use_probability_range else None,
                   probability_max=probability_max if use_probability_range else None)


def _display_group(value: str, dimension: str) -> str:
    if dimension == "turn_phase": return PHASE_LABELS.get(value, value)
    if dimension == "shanten_group": return SHANTEN_LABELS.get(value, value)
    if dimension == "action_category": return ACTION_LABELS.get(value, value)
    if dimension == "riichi_group": return {"none": "なし", "one": "1人", "two_plus": "2人以上"}.get(value, value)
    if dimension == "dealer": return {"dealer": "親", "non_dealer": "子", "unknown": "不明"}.get(value, value)
    if dimension == "bakaze": return {"E": "東場", "S": "南場", "W": "西場", "N": "北場", "unknown": "不明"}.get(value, value)
    if value == "unknown": return "不明"
    return value


def _group_sort_key(value: str, dimension: str) -> tuple[int, str]:
    orders = {
        "turn_phase": {"early": 0, "mid": 1, "late": 2, "unknown": 3},
        "shanten_group": {"tenpai": 0, "one": 1, "two": 2, "three_plus": 3, "negative": 4, "unknown": 5},
        "riichi_group": {"none": 0, "one": 1, "two_plus": 2, "unknown": 3},
        "rank": {"1": 0, "2": 1, "3": 2, "4": 3, "unknown": 4},
    }
    return (orders.get(dimension, {}).get(value, 0 if value == "all" else 1), value)


def _format_action(value: Any) -> str:
    if not value: return "不明"
    if isinstance(value, str): return value
    kind = {"dahai": "打牌", "chi": "チー", "pon": "ポン", "ankan": "暗槓",
            "kakan": "加槓", "daiminkan": "大明槓", "reach": "リーチ", "hora": "和了"}.get(value.get("type"), value.get("type", "不明"))
    pai = value.get("pai") or value.get("consumed") or ""
    return f"{kind} {pai}".strip()


def _display_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "局": f"{item['bakaze'] or '?'}{item['kyoku'] or '?'}局",
        "本場": item["honba"] if item["honba"] is not None else "不明",
        "巡目": item["turn_number"] if item["turn_number"] is not None else "不明",
        "向聴数": item["shanten"] if item["shanten"] is not None else "不明",
        "他家リーチ": item["opponent_riichi_count"] if item["opponent_riichi_count"] is not None else "不明",
        "順位": f"{item['rank']}位" if item["rank"] is not None else "不明",
        "トップとの差": item["gap_to_first"] if item["gap_to_first"] is not None else "不明",
        "本人の選択": _format_action(item["selected_action"]),
        "Mortal第一候補": _format_action(item["mortal_first_action"]),
        "本人の推奨確率": "不明" if item["actual_probability"] is None else f"{item['actual_probability']:.1%}",
        "判定": "一致" if item["is_equal"] is True else "不一致" if item["is_equal"] is False else "判定不能",
    }


def _apply_group_filter(filters: ContextFilters, dimension: str, group: str) -> ContextFilters:
    if dimension == "turn_phase": return replace(filters, turn_phase=group)
    if dimension == "shanten_group": return replace(filters, shanten_group=group)
    if dimension == "action_category": return replace(filters, action_category=None if group == "unknown" else group)
    if dimension == "bakaze": return replace(filters, bakaze=None if group == "unknown" else group)
    if dimension == "dealer": return replace(filters, is_dealer=True if group == "dealer" else False if group == "non_dealer" else None)
    if dimension == "kyoku": return replace(filters, kyoku=None if group == "unknown" else int(group))
    if dimension == "honba": return replace(filters, honba=None if group == "unknown" else int(group))
    if dimension == "rank": return replace(filters, rank=None if group == "unknown" else int(group), rank_unknown=group == "unknown")
    if dimension == "riichi_group": return replace(filters, riichi_count=0 if group == "none" else 1 if group == "one" else None,
                                                    riichi_min=2 if group == "two_plus" else None, riichi_max=None)
    if dimension == "score_diff":
        if group == "0": return replace(filters, score_min=0, score_max=0)
        sign, band = group.split(":", 1)
        if band.endswith("+"):
            lower = int(band[:-1])
            return replace(filters, score_min=None if sign == "behind" else lower,
                           score_max=-lower if sign == "behind" else None)
        lower, upper = (int(value) for value in band.split("-", 1))
        return replace(filters, score_min=-upper if sign == "behind" else lower,
                       score_max=-lower if sign == "behind" else upper)
    return filters


def _home(connection: Any, paths: DashboardPaths) -> None:
    st.title("Mahjong Analyzer")
    data = home_data(connection)
    summaries = data["summaries"]
    decisions = sum(item["total_reviewed"] for item in summaries)
    matches = sum(item["total_matches"] for item in summaries)
    comparable = sum(item["comparable_decisions"] for item in summaries)
    low = sum(item["low_probability_decisions"] for item in summaries)
    st.caption("SQLiteは読み取り専用です。低推奨選択率は客観的な悪手率ではありません。")
    cols = st.columns(3)
    cols[0].metric("解析済み半荘", data["games"])
    cols[1].metric("対象判断", decisions)
    cols[2].metric("AI不一致", decisions - matches)
    cols = st.columns(2)
    cols[0].metric("AI一致率", _rate(matches, decisions))
    cols[1].metric("低推奨選択率", _rate(low, comparable))
    st.subheader("評価条件別の指標")
    st.dataframe([{
        "モデル": item["condition"]["model_tag"] or "不明",
        "reviewer": item["condition"]["reviewer_version"] or "不明",
        "温度": item["condition"]["temperature"], "判断数": item["total_reviewed"],
        "AI一致": f"{item['total_matches']}/{item['total_reviewed']}",
        "低推奨": f"{item['low_probability_decisions']}/{item['comparable_decisions']}",
        "Mortal Rating": ", ".join(f"{x:.4f}" for x in item["ratings"]) or "不明",
    } for item in summaries], width="stretch", hide_index=True)
    with st.expander("ローカル設定・技術情報"):
        st.write("SQLite", str(paths.database)); st.write("レビューJSON", str(paths.review_root)); st.write("元牌譜", str(paths.source_root))
    st.subheader("最近の対局")
    st.dataframe([{"対局": row["id"], "日時": row["played_at"] or "日時不明", "種別": row["game_type"] or "不明"}
                  for row in data["recent_games"]], width="stretch", hide_index=True)
    st.caption("対局日時がDBに保存されていないため、ファイル更新日時や対局IDからは補完していません。")


def _analysis(connection: Any, summaries: list[dict[str, Any]]) -> None:
    st.title("状況別分析")
    filters = _select_condition("analysis", summaries, _filters_from_state(st.session_state.get("analysis_filters")))
    dimension = st.selectbox("分析軸", DIMENSIONS, format_func=DIMENSION_LABELS.get, key="analysis-dimension")
    filters = _filter_controls("analysis", filters)
    bins_text = st.text_input("点数差区間（0から始まるカンマ区切り）", "0,4000,8000,12000", key="analysis-bins")
    try:
        bins = parse_score_bins(bins_text)
        rows = context_data(connection, dimension=dimension, filters=filters,
                            score_target=filters.score_target if dimension == "score_diff" else None, score_bins=bins)
    except (AnalyzerError, ValueError) as exc:
        st.error(str(exc)); return
    rows = sorted(rows, key=lambda row: _group_sort_key(str(row["group"]), dimension))
    if not rows:
        st.info("条件に一致する判断がありません。")
    else:
        st.subheader("全体集計")
        st.dataframe([{"分類": _display_group(row["group"], dimension), "判断数": row["decision_count"],
                       "AI一致": f"{row['agreement_numerator']}/{row['agreement_denominator']}",
                       "AI一致率": "不明" if row["ai_agreement_rate"] is None else f"{row['ai_agreement_rate']:.1%}",
                       "低推奨": f"{row['low_probability_numerator']}/{row['low_probability_denominator']}",
                       "低推奨選択率": "不明" if row["low_recommendation_rate"] is None else f"{row['low_recommendation_rate']:.1%}"}
                      for row in rows], width="stretch", hide_index=True)
        graph_metric = st.selectbox("グラフ指標", list(GRAPH_LABELS), format_func=GRAPH_LABELS.get, key="analysis-graph")
        chart = {"分類": [_display_group(row["group"], dimension) for row in rows],
                 GRAPH_LABELS[graph_metric]: [row[graph_metric] * 100 if graph_metric != "decision_count" and row[graph_metric] is not None else row[graph_metric] for row in rows]}
        st.bar_chart(chart, x="分類", y=GRAPH_LABELS[graph_metric], y_label="%" if graph_metric != "decision_count" else "判断数")
        selected_group = st.selectbox("復習候補へ引き継ぐ分類", [row["group"] for row in rows],
                                      format_func=lambda value: _display_group(value, dimension), key="analysis-group")
        if st.button("この分類・条件で復習候補へ"):
            st.session_state["candidate_filters"] = asdict(_apply_group_filter(filters, dimension, selected_group))
            st.session_state["navigation_target"] = "candidates"; st.rerun()
        st.caption(f"対象判断 {sum(row['decision_count'] for row in rows)}件 / 選択中の1評価条件で合算")
    st.session_state["analysis_filters"] = asdict(filters)


def _candidates(connection: Any, summaries: list[dict[str, Any]]) -> None:
    st.title("復習候補")
    filters = _select_condition("candidate", summaries, _filters_from_state(st.session_state.get("candidate_filters")))
    col1, col2 = st.columns(2)
    with col1: sort = st.selectbox("並び順", list(SORT_LABELS), format_func=SORT_LABELS.get, key="candidate-sort")
    with col2: disagreement_only = st.checkbox("AI不一致だけ", key="candidate-disagreement")
    filters = _filter_controls("candidate", filters)
    signature = json.dumps({**asdict(filters), "sort": sort, "disagreement_only": disagreement_only}, sort_keys=True, default=str)
    if signature != st.session_state.get("candidate-filter-signature"):
        st.session_state["candidate-page"] = 1; st.session_state["candidate-filter-signature"] = signature
    if "candidate-page" not in st.session_state:
        st.session_state["candidate-page"] = 1
    page_size = st.number_input("1ページ件数", min_value=1, max_value=500, value=20, step=1, key="candidate-page-size")
    try:
        preview = candidate_data(connection, sort=sort, filters=filters, disagreement_only=disagreement_only, offset=0, limit=1)
        pages = max(1, math.ceil(preview.total / page_size))
        st.session_state["candidate-page"] = min(st.session_state["candidate-page"], pages)
        page = st.number_input(f"ページ（全{pages}ページ）", min_value=1, max_value=pages,
                               step=1, key="candidate-page")
        result = candidate_data(connection, sort=sort, filters=filters, disagreement_only=disagreement_only,
                                offset=(page - 1) * page_size, limit=page_size)
    except (AnalyzerError, ValueError) as exc:
        st.error(str(exc)); return
    st.write(f"該当 {result.total} 件 / {page}ページ目 / 表示 {len(result.items)} 件")
    st.dataframe([_display_candidate(item) for item in result.items], width="stretch", hide_index=True)
    ids = [item["decision_id"] for item in result.items]
    if ids:
        selected = st.selectbox("詳細を表示する候補", ids, format_func=lambda value: f"decision_id {value}", key="candidate-selection")
        with st.expander("選択候補の技術情報"): st.json(next(item for item in result.items if item["decision_id"] == selected))
        if st.button("局面詳細を開く"):
            st.session_state["selected_decision_id"] = selected; st.session_state["candidate_filters"] = asdict(filters)
            st.session_state["navigation_target"] = "decision"; st.rerun()


def _render_tiles(tile_ids: list[str] | tuple[str, ...] | None, asset_root: Path, *, label: str = "",
                  width: int = 47, show_ids: bool = True, highlight_ids: set[str] | None = None,
                  actual_ids: set[str] | None = None, expected_ids: set[str] | None = None) -> None:
    """Render an allow-listed tile sequence without accepting arbitrary paths."""
    tiles = [tile_id for tile_id in (tile_ids or []) if isinstance(tile_id, str)]
    if label:
        st.caption(label)
    if not tiles:
        st.caption("なし")
        return
    columns = st.columns(len(tiles))
    for column, tile_id in zip(columns, tiles, strict=True):
        try:
            asset = tile_asset(tile_id, asset_root=asset_root)
        except ValueError:
            column.write(tile_id)
            continue
        path = asset.path if asset.path.is_file() else asset_root / "missing.svg"
        column.image(str(path), width=width)
        if show_ids:
            marker = ""
            if highlight_ids and tile_id in highlight_ids:
                marker = " 🔴" if actual_ids and tile_id in actual_ids else " 🟣"
                if expected_ids and tile_id in expected_ids and actual_ids and tile_id in actual_ids:
                    marker = " 🔴🟣"
            column.caption(f"{tile_id}{'（未収録）' if not asset.supported else ''}{marker}")


def _action_tile_ids(action: Any) -> list[str]:
    if not isinstance(action, dict):
        return []
    values: list[str] = []
    if isinstance(action.get("pai"), str):
        values.append(action["pai"])
    consumed = action.get("consumed")
    if isinstance(consumed, list):
        values.extend(value for value in consumed if isinstance(value, str))
    return values


def _render_action(action: Any, asset_root: Path, label: str) -> None:
    st.markdown(f"**{label}**: {_format_action(action)}")
    tile_ids = tile_ids_from_action(action)
    if tile_ids:
        _render_tiles(tile_ids, asset_root)


def _render_river(items: list[dict[str, Any]], asset_root: Path, label: str, *, width: int = 32) -> None:
    tile_ids = [item.get("pai") for item in items if isinstance(item, dict)]
    _render_tiles(tile_ids, asset_root, label=label, width=width, show_ids=False)
    annotations = [f"{item.get('pai', '?')}{'•' if item.get('tsumogiri') else ''}" for item in items]
    if annotations:
        st.caption(" ".join(annotations))


def _render_melds(melds: list[dict[str, Any]], asset_root: Path, label: str, *, width: int = 30) -> None:
    if not melds:
        st.caption(f"{label}: 副露なし")
        return
    for index, meld in enumerate(melds, start=1):
        _render_tiles(tile_ids_from_action(meld), asset_root, label=f"{label} 副露{index}", width=width, show_ids=False)


def _render_table(scene: dict[str, Any], asset_root: Path) -> None:
    st.subheader("麻雀卓")
    st.html(f"<style>{table_css()}</style>{render_table_html(scene, asset_root)}")


def _render_analysis_panel(connection: Any, scene: dict[str, Any], asset_root: Path) -> None:
    st.subheader("Mortal評価")
    previous, following = adjacent_decisions(
        connection, scene["identity"]["decision_id"], disagreement_only=False
    )
    previous_bad, following_bad = adjacent_decisions(
        connection, scene["identity"]["decision_id"], disagreement_only=True
    )
    st.markdown("**判断ナビゲーション**")
    nav1, nav2 = st.columns(2)
    if nav1.button("← 前の判断", disabled=previous is None, key="previous-decision"):
        st.session_state["selected_decision_id"] = previous; st.rerun()
    if nav2.button("次の判断 →", disabled=following is None, key="following-decision"):
        st.session_state["selected_decision_id"] = following; st.rerun()
    nav3, nav4 = st.columns(2)
    if nav3.button("← 前のAI不一致", disabled=previous_bad is None, key="previous-disagreement"):
        st.session_state["selected_decision_id"] = previous_bad; st.rerun()
    if nav4.button("次のAI不一致 →", disabled=following_bad is None, key="following-disagreement"):
        st.session_state["selected_decision_id"] = following_bad; st.rerun()
    if st.button("復習候補一覧へ戻る", key="back-to-candidates"):
        st.session_state["navigation_target"] = "candidates"; st.rerun()
    st.html(f"<style>{table_css()}</style>{render_evaluation_html(scene, asset_root)}")

    with st.expander("開発用の詳細JSON"):
        st.json({"identity": scene["identity"], "round": scene["round"], "hand": scene["hand"],
                 "public": scene["public"], "score": scene["score"], "mortal": scene["mortal"],
                 "none_judgment": scene["none_judgment"]})


def _decision(connection: Any, review_root: Path, source_root: Path, asset_root: Path) -> None:
    st.subheader("局面詳細")
    default_id = st.session_state.get("selected_decision_id", 1)
    id_column, status_column = st.columns([1, 3])
    with id_column:
        decision_id = st.number_input("decision_id", min_value=1, value=default_id, step=1)
    try:
        scene = scene_data(connection, decision_id, review_root=review_root, source_root=source_root)
    except (AnalyzerError, OSError, ValueError) as exc:
        st.error(str(exc)); return
    with status_column:
        st.caption(f"復元状態: {scene['status']}")
    table_column, analysis_column = st.columns([2.25, 1], gap="large")
    with table_column:
        _render_table(scene, asset_root)
    with analysis_column:
        _render_analysis_panel(connection, scene, asset_root)


def main() -> None:
    st.set_page_config(page_title="Mahjong Analyzer", layout="wide", initial_sidebar_state="collapsed")
    project_root = Path(__file__).resolve().parent
    try:
        configured = load_dashboard_paths(project_root / "local_data/config.json", project_root=project_root)
    except ValueError as exc:
        st.error(str(exc)); st.stop()
    st.sidebar.title("Mahjong Analyzer")
    database = Path(st.sidebar.text_input("SQLite", str(configured.database)))
    review_root = Path(st.sidebar.text_input("レビューJSONルート", str(configured.review_root)))
    source_root = Path(st.sidebar.text_input("元牌譜ルート", str(configured.source_root)))
    navigation_target = st.session_state.pop("navigation_target", None)
    if navigation_target in {"home", "analysis", "candidates", "decision"}: st.session_state["page_selector"] = navigation_target
    if "page_selector" not in st.session_state: st.session_state["page_selector"] = "home"
    page = st.sidebar.radio("画面", ["home", "analysis", "candidates", "decision"],
                            format_func={"home": "ホーム", "analysis": "状況別分析", "candidates": "復習候補", "decision": "局面詳細"}.get,
                            key="page_selector")
    try: connection = connect_readonly(database)
    except (OSError, sqlite3.Error) as exc:
        st.error(f"SQLiteを読み込めません。パスとファイルの存在を確認してください: {exc}"); st.stop()
    try:
        summaries = home_data(connection)["summaries"]
        if page == "home": _home(connection, configured)
        elif page == "analysis": _analysis(connection, summaries)
        elif page == "candidates": _candidates(connection, summaries)
        else: _decision(connection, review_root, source_root,
                        project_root / "assets/third_party/mj_king/tiles")
    finally: connection.close()


if __name__ == "__main__": main()
