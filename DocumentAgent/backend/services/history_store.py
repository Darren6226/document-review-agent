"""
历史记录存储模块

使用本地 JSON 文件持久化每次审查的结果，供前端历史记录页面读取。
无需数据库，适合本地自部署场景。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# 历史记录目录与文件
HISTORY_DIR = Path("./history")
HISTORY_FILE = HISTORY_DIR / "history.json"

# 风险等级 -> 展示文案映射（统一给前端用）
RISK_LABELS = {
    "PASSED": "通过",
    "WARNING": "警告",
    "FAILED": "不通过",
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
    "none": "无风险",
}


def _ensure_store() -> None:
    """确保历史记录文件存在，初始化为空列表"""
    HISTORY_DIR.mkdir(exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")


def load_records() -> List[Dict[str, Any]]:
    """读取全部历史记录（最新的排在前面）"""
    _ensure_store()
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return data
    except Exception:
        return []


def save_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """追加一条历史记录（最新的插到最前面）并返回该记录"""
    records = load_records()
    records.insert(0, record)
    HISTORY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record


def get_record(record_id: str) -> Optional[Dict[str, Any]]:
    """按 id 获取单条历史记录详情"""
    for record in load_records():
        if record.get("id") == record_id:
            return record
    return None
