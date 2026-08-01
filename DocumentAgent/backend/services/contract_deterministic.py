"""
合同审核的确定性管线。

体现 Harness Engineering 信条 1「确定性下沉到代码」：
- 金额大小写一致性、日期合法性、条款引用、甲乙方名称一致性
  全部用代码判定，零 LLM、零 token 消耗
- 产出 list[DeterministicFinding]，作为"已知事实"注入给 Agent
  避免 Agent 重复判定这些确定性项

调用链：
  run_deterministic_audit(text)
    -> tools.contract_tools 的底层函数（_extract_* + _verify_*）
    -> 转换为 DeterministicFinding 列表
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.validation import DeterministicFinding
from tools.contract_tools import (
    _extract_amounts,
    _extract_dates,
    _verify_amount_pair,
    _verify_date_parseable,
    _verify_clause_references,
    _verify_party_consistency,
)


def run_deterministic_audit(text: str) -> list[DeterministicFinding]:
    """确定性审核管线：纯代码判定，零 LLM。

    依次执行四类确定性校验：
    1. 金额大小写一致性（同行内的数字金额与中文大写配对校验）
    2. 日期合法性（每个提取到的日期校验是否可解析）
    3. 条款引用准确性（引用的"第X条"是否有对应定义）
    4. 甲乙方名称一致性（全文甲/乙方名称是否统一）

    Args:
        text: 合同文本内容（markdown 或纯文本）

    Returns:
        list[DeterministicFinding]: 确定性校验结果列表
    """
    findings: list[DeterministicFinding] = []

    # 1. 金额大小写一致性：按行号分组，同行内的 numeric 与 chinese 配对校验
    findings.extend(_audit_amount_consistency(text))

    # 2. 日期合法性
    findings.extend(_audit_date_validity(text))

    # 3. 条款引用准确性
    findings.extend(_audit_clause_references(text))

    # 4. 甲乙方名称一致性
    findings.extend(_audit_party_consistency(text))

    return findings


def _audit_amount_consistency(text: str) -> list[DeterministicFinding]:
    """金额大小写一致性校验：同行内的数字金额与中文大写配对。"""
    findings = []
    amounts = _extract_amounts(text)

    # 按 location（行号）分组
    amounts_by_location: dict[str, list] = {}
    for amt in amounts:
        amounts_by_location.setdefault(amt['location'], []).append(amt)

    finding_idx = 0
    for location, amts in amounts_by_location.items():
        numerics = [a for a in amts if a['type'] == 'numeric']
        chinese = [a for a in amts if a['type'] == 'chinese']

        if not numerics or not chinese:
            # 同行没有数字与大写配对，跳过（不报错）
            continue

        # 同行内的 numeric 与 chinese 两两配对校验
        for n in numerics:
            for c in chinese:
                finding_idx += 1
                result = _verify_amount_pair(n['value'], c['raw'])
                findings.append(DeterministicFinding(
                    finding_id=f"DETERM.amount_case.{finding_idx}",
                    rule_id="DETERM.amount_case",
                    rule_category="金额大小写一致性",
                    passed=result['passed'],
                    field=f"{n['raw']} ↔ {c['raw']}",
                    expected=result['expected'],
                    actual=result['actual'],
                    detail=result['detail'] or "大小写金额一致",
                    location=location,
                ))

    return findings


def _audit_date_validity(text: str) -> list[DeterministicFinding]:
    """日期合法性校验：每个提取到的日期校验是否可解析。"""
    findings = []
    dates = _extract_dates(text)

    for i, d in enumerate(dates, 1):
        result = _verify_date_parseable(d['year'], d['month'], d['day'])
        findings.append(DeterministicFinding(
            finding_id=f"DETERM.date_valid.{i}",
            rule_id="DETERM.date_valid",
            rule_category="日期合法性",
            passed=result['passed'],
            field=d['raw'],
            expected=result['expected'],
            actual=result['actual'],
            detail=result['detail'] or "日期合法",
            location=d['location'],
        ))

    return findings


def _audit_clause_references(text: str) -> list[DeterministicFinding]:
    """条款引用准确性校验：引用的"第X条"是否有对应定义。"""
    findings = []
    clause_refs = _verify_clause_references(text)

    for i, ref in enumerate(clause_refs, 1):
        findings.append(DeterministicFinding(
            finding_id=f"DETERM.clause_ref.{i}",
            rule_id="DETERM.clause_ref",
            rule_category="条款引用准确性",
            passed=ref['passed'],
            field=ref['raw'],
            expected="引用的条款存在",
            actual=f"第{ref['ref_id']}条" + ("" if ref['passed'] else "（未找到定义）"),
            detail=ref['detail'] or "条款引用有效",
            location=ref['location'],
        ))

    return findings


def _audit_party_consistency(text: str) -> list[DeterministicFinding]:
    """甲乙方名称一致性校验：全文甲/乙方名称是否统一。"""
    findings = []
    result = _verify_party_consistency(text)

    findings.append(DeterministicFinding(
        finding_id="DETERM.party_consistency.1",
        rule_id="DETERM.party_consistency",
        rule_category="甲乙方名称一致性",
        passed=result['passed'],
        field="甲乙方名称",
        expected="全文名称一致",
        actual=result['detail'] or "名称一致",
        detail=result['detail'] or "甲乙方名称全文一致",
        location="全文",
    ))

    return findings


# ==================== 统计辅助 ====================

def summarize_findings(findings: list[DeterministicFinding]) -> dict:
    """汇总确定性校验结果，供注入 Agent prompt 使用。"""
    total = len(findings)
    passed = len([f for f in findings if f.passed])
    failed = len([f for f in findings if not f.passed])

    by_category: dict[str, dict] = {}
    for f in findings:
        cat = f.rule_category
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "failed": 0}
        by_category[cat]["total"] += 1
        if f.passed:
            by_category[cat]["passed"] += 1
        else:
            by_category[cat]["failed"] += 1

    failed_details = [
        {
            "finding_id": f.finding_id,
            "rule_id": f.rule_id,
            "category": f.rule_category,
            "field": f.field,
            "detail": f.detail,
            "location": f.location,
        }
        for f in findings if not f.passed
    ]

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "by_category": by_category,
        "failed_details": failed_details,
    }


# ==================== 测试 ====================

if __name__ == "__main__":
    test_text = """
劳动合同

甲方：北京某某科技有限公司
乙方：张三

第一条 合同期限
本合同自2024年1月1日起生效，至2027年12月31日止。

第二条 工资待遇
乙方月工资为人民币伍仟元整（5000元），每月15日支付。

第三条 违约责任
如甲方未按时支付工资，应向乙方支付违约金。
详见第五条规定的争议解决方式。（注：第五条不存在）

甲方（签章）：北京某某科技有限公司
"""

    print("=" * 60)
    print("确定性管线测试")
    print("=" * 60)

    findings = run_deterministic_audit(test_text)
    print(f"\n共 {len(findings)} 项确定性校验结果：\n")

    for f in findings:
        status = "✓ PASS" if f.passed else "✗ FAIL"
        print(f"[{status}] {f.finding_id} | {f.rule_category}")
        print(f"  位置: {f.location}")
        print(f"  字段: {f.field}")
        if not f.passed:
            print(f"  详情: {f.detail}")
        print()

    print("=" * 60)
    print("汇总：")
    summary = summarize_findings(findings)
    print(f"  总计: {summary['total']}  通过: {summary['passed']}  失败: {summary['failed']}")
    print(f"  失败项:")
    for d in summary['failed_details']:
        print(f"    - {d['finding_id']}: {d['detail']}")
