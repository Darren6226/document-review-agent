"""
多模型智能路由系统
根据任务类型、复杂度、成本自动选择最优模型

支持：
1. 按任务类型路由（OCR/文本理解/逻辑推理）
2. 按复杂度分级（简单/中等/复杂）
3. 按成本优先级（经济型/平衡型/高性能）
4. 故障自动切换（主→备→兜底）
"""

import os
import hashlib
import redis
import json
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


# ==================== 模型配置 ====================

class ModelTier(str, Enum):
    """模型等级"""
    ECONOMY = "economy"      # 经济型 - 低成本快速任务
    BALANCED = "balanced"    # 平衡型 - 性价比适中
    PERFORMANCE = "performance"  # 高性能 - 复杂核心任务


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    tier: ModelTier
    base_url: str
    api_key_env: str
    max_tokens: int
    temperature: float
    timeout: int
    cost_per_1k: float  # 每 1K tokens 成本（元）
    avg_latency_ms: int  # 平均延迟（毫秒）
    supports_vision: bool  # 是否支持视觉
    context_window: int  # 上下文窗口（tokens）


# 模型配置表
MODEL_REGISTRY: Dict[str, ModelConfig] = {
    # ===== 经济型模型（简单任务）=====
    "qwen-vl-7b": ModelConfig(
        name="Qwen/Qwen2.5-VL-7B-Instruct",
        tier=ModelTier.ECONOMY,
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="OPENAI_API_KEY",
        max_tokens=1000,
        temperature=0.1,
        timeout=30,
        cost_per_1k=0.002,  # 超便宜
        avg_latency_ms=80,
        supports_vision=True,
        context_window=8192
    ),
    
    "internvl-2b": ModelConfig(
        name="OpenGVLab/InternVL2-2B",
        tier=ModelTier.ECONOMY,
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="OPENAI_API_KEY",
        max_tokens=500,
        temperature=0.1,
        timeout=20,
        cost_per_1k=0.001,  # 最便宜
        avg_latency_ms=50,
        supports_vision=True,
        context_window=4096
    ),
    
    # ===== 平衡型模型（中等任务）=====
    "qwen-vl-32b": ModelConfig(
        name="Qwen/Qwen2.5-VL-32B-Instruct",
        tier=ModelTier.BALANCED,
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="OPENAI_API_KEY",
        max_tokens=2000,
        temperature=0.1,
        timeout=60,
        cost_per_1k=0.01,  # 适中
        avg_latency_ms=150,
        supports_vision=True,
        context_window=16384
    ),
    
    # ===== 高性能模型（复杂核心任务）=====
    "qwen-vl-32b": ModelConfig(
        name="Qwen/Qwen3-VL-32B-Instruct",
        tier=ModelTier.PERFORMANCE,
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="OPENAI_API_KEY",
        max_tokens=4000,
        temperature=0.1,
        timeout=120,
        cost_per_1k=0.015,  # 适中
        avg_latency_ms=250,
        supports_vision=True,
        context_window=32768
    ),
    
    "gpt-4o": ModelConfig(
        name="gpt-4o",
        tier=ModelTier.PERFORMANCE,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        max_tokens=4000,
        temperature=0.1,
        timeout=120,
        cost_per_1k=0.15,  # 很贵
        avg_latency_ms=500,
        supports_vision=True,
        context_window=128000
    ),
}


# ==================== 任务分类器 ====================

class TaskType(str, Enum):
    """任务类型"""
    INVOICE_OCR = "invoice_ocr"              # 发票 OCR 识别
    CONTRACT_EXTRACTION = "contract_extraction"  # 合同信息提取
    CONTRACT_AUDIT = "contract_audit"        # 合同专业审查
    INVOICE_VALIDATION = "invoice_validation"  # 发票校验
    SIMPLE_QA = "simple_qa"                  # 简单问答
    COMPLEX_REASONING = "complex_reasoning"  # 复杂推理


@dataclass
class TaskRequirement:
    """任务需求"""
    task_type: TaskType
    input_modality: str  # "text" or "vision"
    estimated_tokens: int
    complexity_score: int  # 1-10，越高越复杂
    latency_requirement: str  # "fast", "normal", "no_limit"
    budget_priority: str  # "high", "medium", "low"
    requires_accuracy: str  # "high", "medium", "low"


def classify_task(task_description: str, input_data: Any) -> TaskRequirement:
    """
    根据任务描述和输入数据，自动分类任务需求
    
    Args:
        task_description: 任务描述文本
        input_data: 输入数据（图片或文本）
        
    Returns:
        TaskRequirement 对象
    """
    # 判断输入模态
    is_image = isinstance(input_data, (str, bytes)) and not isinstance(input_data, str) or \
               (isinstance(input_data, str) and input_data.startswith('data:image'))
    
    # 估算 token 数量
    if is_image:
        estimated_tokens = 2000  # 图片通常消耗更多 tokens
    else:
        estimated_tokens = len(str(input_data)) // 4  # 粗略估算
    
    # 根据关键词判断任务类型
    task_lower = task_description.lower()
    
    if any(kw in task_lower for kw in ['发票', 'ocr', '识别']):
        task_type = TaskType.INVOICE_OCR
        complexity = 3 if estimated_tokens < 1000 else 5
        accuracy_req = "high"
    elif any(kw in task_lower for kw in ['合同', '提取', '关键信息']):
        task_type = TaskType.CONTRACT_EXTRACTION
        complexity = 5
        accuracy_req = "high"
    elif any(kw in task_lower for kw in ['审查', '审核', '风险', '法律']):
        task_type = TaskType.CONTRACT_AUDIT
        complexity = 8
        accuracy_req = "high"
    elif any(kw in task_lower for kw in ['校验', '验证', '检查']):
        task_type = TaskType.INVOICE_VALIDATION
        complexity = 4
        accuracy_req = "medium"
    else:
        task_type = TaskType.SIMPLE_QA
        complexity = 2
        accuracy_req = "low"
    
    # 判断延迟要求
    if "快速" in task_description or "实时" in task_description:
        latency_req = "fast"
    elif "批量" in task_description:
        latency_req = "no_limit"
    else:
        latency_req = "normal"
    
    # 判断预算优先级
    if "测试" in task_description or "demo" in task_description:
        budget_priority = "high"
    elif "生产" in task_description or "正式" in task_description:
        budget_priority = "medium"
    else:
        budget_priority = "low"
    
    return TaskRequirement(
        task_type=task_type,
        input_modality="vision" if is_image else "text",
        estimated_tokens=estimated_tokens,
        complexity_score=complexity,
        latency_requirement=latency_req,
        budget_priority=budget_priority,
        requires_accuracy=accuracy_req
    )


# ==================== 模型路由器 ====================

class ModelRouter:
    """智能模型路由器"""
    
    def __init__(self, use_cache: bool = True):
        """
        初始化路由器
        
        Args:
            use_cache: 是否使用缓存
        """
        self.use_cache = use_cache
        self.model_cache: Dict[str, ChatOpenAI] = {}
        
        # Redis 缓存（可选）
        try:
            self.redis_client = redis.Redis(host='localhost', port=6379, db=1)
            self.has_redis = True
        except:
            self.redis_client = None
            self.has_redis = False
        
        print("✓ 模型路由器初始化完成")
        print(f"  可用模型：{len(MODEL_REGISTRY)} 个")
        print(f"  Redis 缓存：{'已启用' if self.has_redis else '未启用'}")
    
    def select_model(self, requirement: TaskRequirement) -> ModelConfig:
        """
        根据任务需求选择最优模型
        
        决策流程：
        1. 过滤不支持视觉的模型（如果需要）
        2. 过滤上下文窗口不足的模型
        3. 根据复杂度选择对应等级的模型
        4. 根据预算和延迟要求微调
        
        Args:
            requirement: 任务需求
            
        Returns:
            最优模型配置
        """
        print(f"\n🎯 开始模型选择...")
        print(f"  任务类型：{requirement.task_type.value}")
        print(f"  输入模态：{requirement.input_modality}")
        print(f"  预估 Token: {requirement.estimated_tokens}")
        print(f"  复杂度：{requirement.complexity_score}/10")
        
        # Step 1: 初步过滤
        candidates = []
        for model_id, config in MODEL_REGISTRY.items():
            # 视觉能力过滤
            if requirement.input_modality == "vision" and not config.supports_vision:
                continue
            
            # 上下文窗口过滤（留 20% 余量）
            required_context = requirement.estimated_tokens * 1.2
            if config.context_window < required_context:
                continue
            
            candidates.append((model_id, config))
        
        print(f"  通过初步过滤：{len(candidates)} 个候选")
        
        if not candidates:
            # 没有符合条件的，返回最强模型
            print("  ⚠️ 无合适模型，使用默认高性能模型")
            return MODEL_REGISTRY["qwen-vl-72b"]
        
        # Step 2: 根据复杂度评分
        complexity = requirement.complexity_score
        
        if complexity <= 3:
            # 简单任务：优先经济型
            target_tier = ModelTier.ECONOMY
            print("  复杂度低 → 选择经济型模型")
        elif complexity <= 6:
            # 中等任务：优先平衡型
            target_tier = ModelTier.BALANCED
            print("  复杂度中等 → 选择平衡型模型")
        else:
            # 复杂任务：必须高性能
            target_tier = ModelTier.PERFORMANCE
            print("  复杂度高 → 选择高性能模型")
        
        # 过滤出目标等级的模型
        tier_candidates = [
            (mid, cfg) for mid, cfg in candidates
            if cfg.tier == target_tier
        ]
        
        if not tier_candidates:
            # 没有目标等级，向上兼容
            print(f"  ⚠️ 无{target_tier.value}模型，向上兼容")
            if target_tier == ModelTier.ECONOMY:
                tier_candidates = [(mid, cfg) for mid, cfg in candidates if cfg.tier == ModelTier.BALANCED]
            elif target_tier == ModelTier.BALANCED:
                tier_candidates = [(mid, cfg) for mid, cfg in candidates if cfg.tier == ModelTier.PERFORMANCE]
        
        if not tier_candidates:
            # 最后兜底
            tier_candidates = candidates
        
        # Step 3: 在同等級中按成本和延迟排序
        def score_model(item):
            model_id, config = item
            score = 0
            
            # 成本分数（越低越好）
            score += config.cost_per_1k * 100
            
            # 延迟分数（越低越好）
            score += config.avg_latency_ms / 100
            
            # 预算优先级调整
            if requirement.budget_priority == "high":
                score *= 0.5  # 更看重成本
            elif requirement.budget_priority == "low":
                score *= 1.5  # 不太看重成本
            
            return score
        
        # 排序并选择最优
        tier_candidates.sort(key=score_model)
        best_model_id, best_config = tier_candidates[0]
        
        print(f"  ✓ 选定模型：{best_model_id}")
        print(f"     等级：{best_config.tier.value}")
        print(f"     成本：¥{best_config.cost_per_1k:.4f}/1K tokens")
        print(f"     延迟：~{best_config.avg_latency_ms}ms")
        
        return best_config
    
    def get_llm(self, model_config: ModelConfig) -> ChatOpenAI:
        """
        获取或创建 LLM 实例
        
        Args:
            model_config: 模型配置
            
        Returns:
            ChatOpenAI 实例
        """
        # 检查缓存
        cache_key = f"llm:{model_config.name}"
        
        if self.use_cache and cache_key in self.model_cache:
            print(f"  ♻️ 使用缓存的 LLM 实例：{model_config.name}")
            return self.model_cache[cache_key]
        
        # 获取 API Key
        api_key = os.getenv(model_config.api_key_env)
        if not api_key:
            raise ValueError(f"未设置 API Key: {model_config.api_key_env}")
        
        # 创建新实例
        llm = ChatOpenAI(
            model=model_config.name,
            api_key=api_key,
            base_url=model_config.base_url,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature,
            timeout=model_config.timeout
        )
        
        # 写入缓存
        if self.use_cache:
            self.model_cache[cache_key] = llm
            print(f"  💾 创建并缓存 LLM 实例：{model_config.name}")
        
        return llm
    
    def invoke_with_fallback(
        self,
        requirement: TaskRequirement,
        messages: List,
        fallback_chain: Optional[List[str]] = None
    ) -> Any:
        """
        调用模型，带降级机制
        
        Args:
            requirement: 任务需求
            messages: 消息列表
            fallback_chain: 降级模型链（可选）
            
        Returns:
            模型响应
        """
        # 默认降级链：主选 → 同级备选 → 上一级 → 最强兜底
        if fallback_chain is None:
            fallback_chain = [
                "qwen-vl-72b",  # 最终兜底
                "qwen-vl-32b",
                "qwen-vl-7b"
            ]
        
        # Step 1: 选择主模型
        primary_model = self.select_model(requirement)
        
        # Step 2: 尝试调用
        attempt_count = 0
        max_attempts = len(fallback_chain) + 1
        
        for attempt in range(max_attempts):
            attempt_count += 1
            
            try:
                print(f"\n🔄 尝试 #{attempt_count}: {primary_model.name}")
                
                # 获取 LLM
                llm = self.get_llm(primary_model)
                
                # 调用
                start_time = __import__('time').time()
                response = llm.invoke(messages)
                elapsed = __import__('time').time() - start_time
                
                print(f"  ✓ 成功！耗时：{elapsed:.2f}s")
                return response
                
            except Exception as e:
                print(f"  ❌ 失败：{str(e)[:100]}")
                
                # 查找下一个可用模型
                next_model_found = False
                for fallback_id in fallback_chain:
                    if fallback_id in MODEL_REGISTRY:
                        primary_model = MODEL_REGISTRY[fallback_id]
                        next_model_found = True
                        break
                
                if not next_model_found:
                    print("  ⚠️ 无可用降级模型")
                    break
        
        # 全部失败
        raise RuntimeError(f"模型调用失败，已尝试{attempt_count}次")


# ==================== 缓存装饰器 ====================

def cache_result(ttl_seconds: int = 3600):
    """
    缓存 LLM 调用结果的装饰器
    
    Args:
        ttl_seconds: 缓存时间（秒）
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key_data = json.dumps({
                "args": str(args),
                "kwargs": str(kwargs)
            }, ensure_ascii=False)
            
            cache_key = f"llm_result:{hashlib.md5(cache_key_data.encode()).hexdigest()}"
            
            # 尝试从 Redis 获取
            router = args[0] if args else None
            if isinstance(router, ModelRouter) and router.has_redis:
                cached = router.redis_client.get(cache_key)
                if cached:
                    print(f"  ♻️ 命中缓存结果")
                    return json.loads(cached)
            
            # 调用原函数
            result = func(*args, **kwargs)
            
            # 写入缓存
            if isinstance(router, ModelRouter) and router.has_redis:
                router.redis_client.setex(
                    cache_key,
                    ttl_seconds,
                    json.dumps(result, ensure_ascii=False)
                )
            
            return result
        return wrapper
    return decorator


# ==================== 使用示例 ====================

class MultiModelInvoiceSystem:
    """多模型发票识别系统（演示）"""
    
    def __init__(self):
        self.router = ModelRouter(use_cache=True)
    
    @cache_result(ttl_seconds=86400)  # 缓存 24 小时
    def recognize_invoice(self, image_data: str) -> dict:
        """
        识别发票（自动选择模型）
        
        Args:
            image_data: Base64 编码的图片
            
        Returns:
            发票数据字典
        """
        # 分类任务需求
        requirement = classify_task(
            "发票 OCR 识别，提取所有字段",
            image_data
        )
        
        # 构建消息
        prompt = """你是专业的发票识别助手。请识别这张发票并返回 JSON 格式的所有字段。"""
        
        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
            }
        ])
        
        # 调用模型（带降级）
        response = self.router.invoke_with_fallback(
            requirement=requirement,
            messages=[message]
        )
        
        # 解析 JSON
        return self._extract_json(response.content)
    
    def _extract_json(self, text: str) -> dict:
        """三重容错 JSON 提取"""
        import re
        import json
        
        # 尝试 1: 直接解析
        try:
            return json.loads(text)
        except:
            pass
        
        # 尝试 2: 提取 Markdown 代码块
        match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except:
                pass
        
        # 尝试 3: 匹配 JSON 对象
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        
        raise ValueError(f"无法提取 JSON: {text[:200]}")


# ==================== 主函数（测试） ====================

if __name__ == "__main__":
    print("=" * 70)
    print("多模型智能路由系统 - 演示")
    print("=" * 70)
    
    # 创建路由器
    router = ModelRouter(use_cache=True)
    
    # 测试场景 1: 简单发票识别
    print("\n\n【场景 1】简单发票识别（经济型）")
    req1 = classify_task("发票 OCR 识别", "data:image/jpeg;base64,...")
    model1 = router.select_model(req1)
    print(f"选定：{model1.name} (成本：¥{model1.cost_per_1k:.4f})")
    
    # 测试场景 2: 合同审查
    print("\n\n【场景 2】合同专业审查（高性能）")
    req2 = classify_task("合同法律风险审查，检查所有条款", "合同文本...")
    model2 = router.select_model(req2)
    print(f"选定：{model2.name} (成本：¥{model2.cost_per_1k:.4f})")
    
    # 测试场景 3: 发票校验
    print("\n\n【场景 3】发票数据校验（平衡型）")
    req3 = classify_task("发票完整性校验和格式验证", {"invoice_code": "..."})
    model3 = router.select_model(req3)
    print(f"选定：{model3.name} (成本：¥{model3.cost_per_1k:.4f})")
    
    print("\n" + "=" * 70)
    print("✅ 演示完成！")
    print("=" * 70)
    
    print("\n💡 关键优势:")
    print("1. 简单任务用小模型，成本降低 60%+")
    print("2. 复杂任务用大模型，保证质量")
    print("3. 自动降级切换，提高稳定性")
    print("4. 支持缓存，进一步降低成本")
    print("\n📊 成本对比:")
    print("  单模型方案：1000 次调用 × ¥0.02 = ¥20")
    print("  多模型方案：600 次×¥0.002 + 300 次×¥0.01 + 100 次×¥0.02 = ¥5.2")
    print("  节省：¥14.8 (74%)")
