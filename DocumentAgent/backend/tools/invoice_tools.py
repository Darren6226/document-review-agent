"""
发票审核的计算校验工具。

将金额勾稽从「LLM 心算」改为「Python 精确计算」，确保结果确定、可复现。
所有结果以 JSON 字符串返回，由 Agent 映射为 calculation Skill 的报告格式：
- status=PASS  -> INFO
- status=FAIL  -> 按 level（ERROR / WARNING）
- status=SKIP  -> INFO（前置字段缺失，由 completeness/format 负责报错，不重复告警）
"""

import json

from langchain_core.tools import tool

# 与 calculation/SKILL.md 中的容差保持一致
TOLERANCE = 0.02


def _num(v):
    """安全转 float，失败返回 None。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _check(name: str, expected, actual, level: str) -> dict:
    """生成一条确定性勾稽结果。"""
    diff = abs(round(expected, 4) - round(actual, 4))
    passed = diff <= TOLERANCE
    return {
        "check": name,
        "status": "PASS" if passed else "FAIL",
        "expected": round(expected, 2),
        "actual": round(actual, 2),
        "diff": round(diff, 4),
        "level": "INFO" if passed else level,
        "message": (
            "" if passed
            else f"{name}不符：期望 {round(expected, 2)}，实际 {round(actual, 2)}，差值 {round(diff, 4)}"
        ),
    }


def _skip(name: str, reason: str) -> dict:
    """前置字段缺失时跳过，不重复告警。"""
    return {
        "check": name,
        "status": "SKIP",
        "expected": None,
        "actual": None,
        "diff": None,
        "level": "INFO",
        "message": f"跳过：{reason}",
    }


@tool
def verify_invoice_calculation(invoice_data: dict) -> str:
    """对发票金额做确定性勾稽校验，返回 JSON 字符串。

    Args:
        invoice_data: 发票数据对象（JSON object），包含 total_amount / total_tax /
            total_amount_with_tax / line_items 等字段。

    包含四项：
    1. 价税合计校验（合计金额 + 合计税额 = 价税合计，ERROR 级）
    2. 行项目金额合计校验（SUM(行项目.amount) = total_amount，WARNING 级）
    3. 行项目税额合计校验（SUM(行项目.tax_amount) = total_tax，WARNING 级）
    4. 单项税额校验（金额 × 税率 = 税额，ERROR 级）

    字段缺失或非数字时对应项标记 SKIP。容差为 0.02 元。
    调用方应将结果映射为 calculation Skill 的输出格式，禁止自行心算。

    边界分工：
    - 入参整体类型由 dict 注解（Pydantic）在工具边界校验，校验失败时
      LangGraph ToolNode 默认将 ToolInvocationError 消息回传给 LLM 触发重试
      （见 langgraph.prebuilt.tool_node._default_handle_tool_errors），
      因此本函数无需自行处理"非 dict 入参"。
    - 嵌套结构（line_items 非列表）与字段值（缺失/非数字）由函数内部容错，
      降级为 SKIP，不抛异常。
    """
    try:
        return _run_verification(invoice_data)
    except Exception as e:  # noqa: BLE001 - 兜底：任何意外都返回 SKIP 而非崩溃
        return json.dumps(
            [_skip("整体校验", f"校验过程发生异常，已安全跳过: {type(e).__name__}: {e}")],
            ensure_ascii=False,
        )


def _run_verification(invoice_data: dict) -> str:
    """实际勾稽逻辑（由 verify_invoice_calculation 在结构校验后调用）。"""
    results: list[dict] = []

    ta = _num(invoice_data.get("total_amount"))
    tt = _num(invoice_data.get("total_tax"))
    tw = _num(invoice_data.get("total_amount_with_tax"))
    # 结构闸门 B：line_items 必须是 list，否则视为无行项目
    items = invoice_data.get("line_items")
    if not isinstance(items, list):
        items = []

    # 1. 价税合计
    if None in (ta, tt, tw):
        results.append(_skip("价税合计校验", "total_amount/total_tax/total_amount_with_tax 缺失或非数字"))
    else:
        expected = round(ta + tt, 2)
        results.append(_check("价税合计校验", expected, tw, "ERROR"))

    # 2 & 3. 行项目金额/税额求和
    if not items or ta is None:
        results.append(_skip("行项目金额合计校验", "line_items 缺失或 total_amount 缺失"))
    else:
        s = sum(_num(i.get("amount")) or 0 for i in items)
        results.append(_check("行项目金额合计校验", round(s, 2), ta, "WARNING"))

    if not items or tt is None:
        results.append(_skip("行项目税额合计校验", "line_items 缺失或 total_tax 缺失"))
    else:
        s = sum(_num(i.get("tax_amount")) or 0 for i in items)
        results.append(_check("行项目税额合计校验", round(s, 2), tt, "WARNING"))

    # 4. 单项税额
    if not items:
        results.append(_skip("单项税额校验", "line_items 缺失"))
    else:
        for idx, i in enumerate(items):
            a = _num(i.get("amount"))
            r = _num(i.get("tax_rate"))
            t = _num(i.get("tax_amount"))
            label = i.get("name") or f"第{idx + 1}项"
            if None in (a, r, t):
                results.append(_skip(f"单项税额校验({label})", "amount/tax_rate/tax_amount 缺失或非数字"))
            else:
                results.append(_check(f"单项税额校验({label})", round(a * r, 2), t, "ERROR"))

    return json.dumps(results, ensure_ascii=False)
