"""
合同审核的确定性校验工具。

体现 Harness Engineering 信条 1「确定性下沉到代码」：
- 金额大小写一致性、日期合法性、条款编号引用、甲乙方名称一致性
  全部用代码判定，不让 LLM 心算
- 提取层（extract_*）与校验层（verify_*）分离，支持 Agent 精细推理
  （优化 6：LLM 可先 extract 看全局，再对可疑项逐个 verify）

提取层返回结构化数据（list[dict]），校验层返回判定结果（dict）。
@tool 装饰的版本供 Agent 调用，返回 JSON 字符串；
以 _ 开头的底层函数供确定性管线（contract_deterministic.py）直接调用。
"""

import re
import json
from datetime import datetime
from langchain_core.tools import tool


# ==================== 中文金额解析 ====================

# 中文数字映射（含大写形式）
CHINESE_DIGITS = {
    '零': 0, '〇': 0, '一': 1, '壹': 1, '二': 2, '贰': 2, '两': 2, '三': 3, '叁': 3,
    '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6, '七': 7, '柒': 7,
    '八': 8, '捌': 8, '九': 9, '玖': 9,
}

# 中文单位映射
CHINESE_UNITS = {
    '十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000,
    '万': 10000, '萬': 10000, '亿': 100000000, '億': 100000000,
}


def chinese_to_number(chinese_str: str) -> float | None:
    """将中文金额大写转换为数字。

    支持：壹万贰仟叁佰元整、一万二千三百、伍仟元 等
    无法解析的返回 None。
    """
    if not chinese_str:
        return None

    # 清理：去掉元/圆/整/正/角/分/人民币 等非数字字符
    cleaned = re.sub(r'[人民币元圆整正角分¥￥,，\s]', '', chinese_str)
    if not cleaned:
        return None

    total = 0.0
    current = 0      # 当前数字
    section = 0      # 万/亿分段前的累计值

    for char in cleaned:
        if char in CHINESE_DIGITS:
            current = CHINESE_DIGITS[char]
        elif char in CHINESE_UNITS:
            unit = CHINESE_UNITS[char]
            if unit >= 10000:
                # 万/亿：先结算当前 section，再乘以大单位
                section = (section + current) * unit
                total += section
                section = 0
                current = 0
            else:
                # 十百千：当前数字乘以单位，累加到 section
                if current == 0:
                    current = 1  # "十" 单独出现表示 10
                section += current * unit
                current = 0
        else:
            # 遇到无法识别的字符，返回 None
            return None

    result = total + section + current
    return result if result > 0 else None


# ==================== 位置与上下文辅助 ====================

def _find_line_number(text: str, pos: int) -> int:
    """根据字符位置返回行号（从 1 开始）。"""
    return text.count('\n', 0, pos) + 1


def _find_context(text: str, pos: int, context_len: int = 20) -> str:
    """返回位置周围的上下文文本（去除换行，便于阅读）。"""
    start = max(0, pos - context_len)
    end = min(len(text), pos + context_len)
    return text[start:end].replace('\n', ' ').strip()


# ==================== 提取层（底层函数，供管线直接调用） ====================

# 合同主体角色标签：真实主体名称不会以这些标签开头，
# 若捕获到的"名称"以角色标签开头，说明是从签章合并行误捕了对方标签（如"甲方（盖章）： 乙方（签字）："）
ROLE_LABELS = ['甲方', '乙方', '丙方', '丁方']


def _is_valid_party_name(name: str) -> bool:
    """判断提取到的主体名称是否合法。

    过滤两类误捕：
    1. 空名称或仅空白/标点；
    2. 以角色标签（甲方/乙方/丙方/丁方）开头 —— 通常是签章合并行
       "甲方（盖章）： 乙方（签字）：" 把对方标签当成了本方名称。
    """
    s = (name or "").strip()
    if not s:
        return False
    if any(s.startswith(label) for label in ROLE_LABELS):
        return False
    return True


def _extract_amounts(text: str) -> list[dict]:
    """提取所有金额（阿拉伯数字 + 中文大写），带位置信息。"""
    results = []

    # 模式 1：阿拉伯数字金额（如 5000元、¥5000、5,000.00元、5000.00元）
    numeric_pattern = re.compile(r'[¥￥]?\s*([\d,]+\.?\d*)\s*[元圆]')
    for m in numeric_pattern.finditer(text):
        num_str = m.group(1).replace(',', '')
        try:
            value = float(num_str)
            results.append({
                'type': 'numeric',
                'value': value,
                'raw': m.group(0).strip(),
                'location': f"第{_find_line_number(text, m.start())}行",
                'context': _find_context(text, m.start()),
            })
        except ValueError:
            continue

    # 模式 2：中文大写金额（如 人民币伍仟元整、壹万贰仟元）
    chinese_pattern = re.compile(
        r'(?:人民币)?\s*'
        r'([零〇壹贰叁肆伍陆柒捌玖拾佰仟万亿萬億两一二三四五六七八九十百千万]+'
        r'\s*[元圆](?:整|正)?)'
    )
    for m in chinese_pattern.finditer(text):
        raw = m.group(0).strip()
        chinese_part = m.group(1)
        value = chinese_to_number(chinese_part)
        if value is not None:
            results.append({
                'type': 'chinese',
                'value': value,
                'raw': raw,
                'location': f"第{_find_line_number(text, m.start())}行",
                'context': _find_context(text, m.start()),
            })

    return results


def _extract_dates(text: str) -> list[dict]:
    """提取所有日期，带位置信息。"""
    results = []
    seen_positions = set()

    patterns = [
        # 2024年1月1日 / 2024年01月01日
        (re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日'), 'chinese'),
        # 2024-01-01 / 2024-1-1
        (re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})'), 'iso'),
        # 2024/01/01
        (re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})'), 'slash'),
    ]

    for pattern, fmt in patterns:
        for m in pattern.finditer(text):
            # 避免重复匹配同一位置
            pos_range = range(m.start(), m.end())
            if any(p in seen_positions for p in pos_range):
                continue
            seen_positions.update(pos_range)

            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            results.append({
                'raw': m.group(0),
                'format': fmt,
                'year': year,
                'month': month,
                'day': day,
                'location': f"第{_find_line_number(text, m.start())}行",
                'context': _find_context(text, m.start()),
            })

    return results


def _extract_clauses(text: str) -> list[dict]:
    """提取所有条款编号（如 第一条、第3条、3.1），带位置信息。"""
    results = []

    patterns = [
        # 第一条 / 第3条 / 第一百零一条
        (re.compile(r'第([一二三四五六七八九十百零\d]+)条'), 'chapter'),
        # 3.1 / 3.1.1（条款编号，需前后非数字，避免匹配日期）
        (re.compile(r'(?<!\d)(\d+\.\d+(?:\.\d+)?)(?!\d)'), 'decimal'),
    ]

    for pattern, kind in patterns:
        for m in pattern.finditer(text):
            results.append({
                'kind': kind,
                'ref_id': m.group(1),
                'raw': m.group(0),
                'location': f"第{_find_line_number(text, m.start())}行",
                'context': _find_context(text, m.start()),
            })

    return results


def _extract_parties(text: str) -> list[dict]:
    """提取甲乙方名称，带位置信息。"""
    results = []

    # 甲方：XXX / 甲方(出租方)：XXX / 甲方（签章）：XXX
    # 要求必须有冒号，避免"乙方月工资..."被误匹配
    # 名称捕获组排除空白：签章合并行"甲方（盖章）： 乙方（签字）："中冒号后是空格，
    # 不会把"乙方"误捕为甲方名称；同时再用 _is_valid_party_name 兜底过滤角色标签前缀
    for role, pattern in [
        ('party_a', re.compile(r'甲[方](?:\s*[（(][^）)]*[）)])?\s*[:：]\s*([^\n\s，,。.；;（(]{2,50})')),
        ('party_b', re.compile(r'乙[方](?:\s*[（(][^）)]*[）)])?\s*[:：]\s*([^\n\s，,。.；;（(]{2,50})')),
    ]:
        for m in pattern.finditer(text):
            name = m.group(1).strip()
            # 跳过非法名称（空名称 / 被误捕为名称的角色标签）
            if not _is_valid_party_name(name):
                continue
            results.append({
                'role': role,
                'name': name,
                'raw': m.group(0).strip(),
                'location': f"第{_find_line_number(text, m.start())}行",
                'context': _find_context(text, m.start()),
            })

    return results


# ==================== 校验层（底层函数，供管线直接调用） ====================

def _verify_amount_pair(amount_numeric: float, amount_in_words: str) -> dict:
    """校验数字金额与中文大写金额是否一致。"""
    chinese_value = chinese_to_number(amount_in_words)
    if chinese_value is None:
        return {
            'passed': False,
            'detail': f"无法解析中文大写金额：{amount_in_words}",
            'expected': amount_numeric,
            'actual': None,
        }

    # 容差 0.02 元（与 invoice_tools 保持一致）
    diff = abs(amount_numeric - chinese_value)
    passed = diff <= 0.02
    return {
        'passed': passed,
        'detail': '' if passed else f"大小写不一致：数字 {amount_numeric}，大写解析为 {chinese_value}，差值 {round(diff, 2)}",
        'expected': amount_numeric,
        'actual': chinese_value,
    }


def _verify_date_parseable(year: int, month: int, day: int) -> dict:
    """校验日期是否合法可解析。"""
    try:
        datetime(year=year, month=month, day=day)
        return {
            'passed': True,
            'detail': '',
            'expected': f"{year}-{month:02d}-{day:02d}",
            'actual': f"{year}-{month:02d}-{day:02d}",
        }
    except (ValueError, TypeError) as e:
        return {
            'passed': False,
            'detail': f"日期不合法：{year}年{month}月{day}日 - {e}",
            'expected': '合法日期',
            'actual': f"{year}-{month}-{day}",
        }


def _verify_clause_references(text: str) -> list[dict]:
    """校验条款编号引用是否都有对应条款定义。

    如"详见第三条"中的"第三条"必须存在条款标题"第三条 XXX"。
    """
    results = []

    # 找出所有"第X条"的引用（如：详见第三条、按照第五条规定、根据第七条）
    ref_pattern = re.compile(r'(?:详见|按照|根据|参照|见|依|遵守)\s*第([一二三四五六七八九十百零\d]+)条')
    # 找出所有条款标题定义（行首的"第X条"，避免把引用中的"第X条"误认为定义）
    def_pattern = re.compile(r'(?m)^\s*第([一二三四五六七八九十百零\d]+)条')

    defined = set(m.group(1) for m in def_pattern.finditer(text))

    for m in ref_pattern.finditer(text):
        ref_id = m.group(1)
        location = f"第{_find_line_number(text, m.start())}行"
        results.append({
            'passed': ref_id in defined,
            'ref_id': ref_id,
            'raw': m.group(0),
            'location': location,
            'detail': '' if ref_id in defined else f"引用了第{ref_id}条，但未找到对应条款定义",
        })

    return results


def _verify_party_consistency(text: str) -> dict:
    """校验甲乙方名称在全文中是否一致。"""
    parties = _extract_parties(text)

    party_a_names = [p['name'] for p in parties if p['role'] == 'party_a']
    party_b_names = [p['name'] for p in parties if p['role'] == 'party_b']

    issues = []

    unique_a = set(party_a_names)
    if len(unique_a) > 1:
        issues.append({
            'role': 'party_a',
            'detail': f"甲方名称不一致：{list(unique_a)}",
            'names': list(unique_a),
        })

    unique_b = set(party_b_names)
    if len(unique_b) > 1:
        issues.append({
            'role': 'party_b',
            'detail': f"乙方名称不一致：{list(unique_b)}",
            'names': list(unique_b),
        })

    if not issues:
        return {
            'passed': True,
            'detail': '',
            'party_a_count': len(party_a_names),
            'party_b_count': len(party_b_names),
            'party_a_unique': len(unique_a),
            'party_b_unique': len(unique_b),
        }

    return {
        'passed': False,
        'detail': '; '.join(i['detail'] for i in issues),
        'party_a_count': len(party_a_names),
        'party_b_count': len(party_b_names),
        'issues': issues,
    }


# ==================== Agent 工具（@tool 装饰，返回 JSON 字符串） ====================

@tool
def extract_amounts(text: str) -> str:
    """从合同文本中提取所有金额（阿拉伯数字 + 中文大写），返回 JSON 字符串。

    每个金额包含：type(numeric/chinese)、value、raw、location、context。
    用于金额相关校验的前置提取。建议先调用此工具查看全文金额分布，
    再对可疑项调用 verify_amount_pair 逐个校验。

    Args:
        text: 合同文本内容
    """
    return json.dumps(_extract_amounts(text), ensure_ascii=False)


@tool
def extract_dates(text: str) -> str:
    """从合同文本中提取所有日期，返回 JSON 字符串。

    每个日期包含：raw、format(chinese/iso/slash)、year、month、day、location、context。
    用于日期格式与合法性校验的前置提取。

    Args:
        text: 合同文本内容
    """
    return json.dumps(_extract_dates(text), ensure_ascii=False)


@tool
def extract_clauses(text: str) -> str:
    """从合同文本中提取所有条款编号，返回 JSON 字符串。

    每个条款包含：kind(chapter/decimal)、ref_id、raw、location、context。
    用于条款引用准确性校验的前置提取。

    Args:
        text: 合同文本内容
    """
    return json.dumps(_extract_clauses(text), ensure_ascii=False)


@tool
def extract_parties(text: str) -> str:
    """从合同文本中提取甲乙方名称，返回 JSON 字符串。

    每个主体包含：role(party_a/party_b)、name、raw、location、context。
    用于名称一致性校验的前置提取。

    Args:
        text: 合同文本内容
    """
    return json.dumps(_extract_parties(text), ensure_ascii=False)


@tool
def verify_amount_pair(amount_numeric: float, amount_in_words: str) -> str:
    """校验数字金额与中文大写金额是否一致。

    Args:
        amount_numeric: 数字金额（如 5000.00）
        amount_in_words: 中文大写金额（如"伍仟元整"）

    返回 JSON：{passed, detail, expected, actual}
    """
    result = _verify_amount_pair(amount_numeric, amount_in_words)
    return json.dumps(result, ensure_ascii=False)


@tool
def verify_date_parseable(year: int, month: int, day: int) -> str:
    """校验日期是否合法可解析。

    Args:
        year: 年（如 2024）
        month: 月（如 1 或 01）
        day: 日（如 1 或 01）

    返回 JSON：{passed, detail, expected, actual}
    """
    result = _verify_date_parseable(year, month, day)
    return json.dumps(result, ensure_ascii=False)


@tool
def verify_clause_reference(text: str) -> str:
    """校验合同文本中的条款编号引用是否都有对应条款定义。

    如"详见第三条"必须存在条款标题"第三条"。
    返回 JSON 数组，每个元素：{passed, ref_id, raw, location, detail}

    Args:
        text: 合同文本内容
    """
    results = _verify_clause_references(text)
    return json.dumps(results, ensure_ascii=False)


@tool
def verify_party_consistency(text: str) -> str:
    """校验甲乙方名称在全文中是否一致。

    Args:
        text: 合同文本内容

    返回 JSON：{passed, detail, party_a_count, party_b_count, issues?}
    """
    result = _verify_party_consistency(text)
    return json.dumps(result, ensure_ascii=False)
