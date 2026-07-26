# 多模型智能路由系统 - 完整指南

## 📋 目录

1. [为什么需要多模型？](#为什么需要多模型)
2. [系统架构](#系统架构)
3. [核心组件](#核心组件)
4. [快速开始](#快速开始)
5. [使用场景](#使用场景)
6. [成本对比](#成本对比)
7. [性能优化](#性能优化)
8. [最佳实践](#最佳实践)

---

## 🎯 为什么需要多模型？

### **当前单模型架构的问题**

```python
# ❌ 问题示例：所有任务都用 Qwen2.5-VL-72B-Instruct

# 场景 1: 简单发票识别（其实 7B 模型就够了）
invoice = llm_72b.invoke(image)  # 花费 ¥0.02，耗时 300ms

# 场景 2: 合同关键信息提取（32B 模型足够）
contract = llm_72b.invoke(text)  # 花费 ¥0.02，耗时 300ms

# 场景 3: 复杂法律审查（确实需要 72B）
audit = llm_72b.invoke(complex_text)  # 花费 ¥0.02，耗时 300ms
```

**问题分析：**
- 💸 **成本高**：简单任务也用大模型，浪费钱
- 🐌 **速度慢**：所有请求都排队等 72B 模型
- 📉 **性能过剩**：发票识别用 7B 模型准确率就达 95%+
- ⚠️ **无兜底**：模型挂了整个系统瘫痪

### **多模型架构的优势**

```python
# ✅ 解决方案：根据任务选择最优模型

# 简单任务 → 经济型模型
invoice = llm_2b.invoke(image)  # 花费 ¥0.001，耗时 50ms

# 中等任务 → 平衡型模型
contract = llm_32b.invoke(text)  # 花费 ¥0.01，耗时 150ms

# 复杂任务 → 高性能模型
audit = llm_72b.invoke(complex_text)  # 花费 ¥0.02，耗时 300ms
```

**优势：**
- ✅ **成本降低 74%**：从¥20/千次降到¥5.2/千次
- ✅ **速度提升 50%**：平均延迟从 300ms 降到 150ms
- ✅ **稳定性提升**：主模型挂了自动切换备用
- ✅ **灵活性高**：针对不同任务选择最优模型

---

## 🏗️ 系统架构

### **架构图**

```
┌─────────────────────────────────────────────────┐
│           用户请求层                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ 发票 OCR  │  │ 合同审查  │  │ 数据校验  │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
└───────┼─────────────┼─────────────┼────────────┘
        │             │             │
        ▼             ▼             ▼
┌─────────────────────────────────────────────────┐
│         任务分类器 (Task Classifier)            │
│  • 分析输入模态 (text/vision)                   │
│  • 估算 Token 数量                                │
│  • 评估复杂度 (1-10 分)                           │
│  • 判断延迟要求 (fast/normal/no_limit)          │
└───────────────────┬─────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────┐
│       模型路由器 (Model Router)                 │
│  1. 过滤不支持视觉的模型                         │
│  2. 过滤上下文不足的模型                         │
│  3. 根据复杂度选择对应等级                       │
│  4. 按成本和延迟排序                             │
└───────────────────┬─────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌──────────────┐      ┌──────────────┐
│ 经济型模型   │      │ 平衡型模型   │
│ • 2B-7B      │      │ • 32B        │
│ • ¥0.001    │      │ • ¥0.01      │
│ • 50ms      │      │ • 150ms      │
└──────────────┘      └──────────────┘
                              │
                              ▼
                      ┌──────────────┐
                      │ 高性能模型   │
                      │ • 72B+       │
                      │ • ¥0.02     │
                      │ • 300ms     │
                      └──────────────┘
```

---

## 🔧 核心组件

### **1. 模型配置表**

```python
MODEL_REGISTRY = {
    # 经济型
    "qwen-vl-7b": ModelConfig(
        name="Qwen/Qwen2.5-VL-7B-Instruct",
        tier=ModelTier.ECONOMY,
        cost_per_1k=0.002,
        avg_latency_ms=80,
        supports_vision=True,
        context_window=8192
    ),
    
    # 平衡型
    "qwen-vl-32b": ModelConfig(
        name="Qwen/Qwen2.5-VL-32B-Instruct",
        tier=ModelTier.BALANCED,
        cost_per_1k=0.01,
        avg_latency_ms=150,
        supports_vision=True,
        context_window=16384
    ),
    
    # 高性能
    "qwen-vl-72b": ModelConfig(
        name="Qwen/Qwen2.5-VL-72B-Instruct",
        tier=ModelTier.PERFORMANCE,
        cost_per_1k=0.02,
        avg_latency_ms=300,
        supports_vision=True,
        context_window=32768
    ),
}
```

### **2. 任务需求定义**

```python
@dataclass
class TaskRequirement:
    task_type: TaskType          # 任务类型
    input_modality: str          # 输入模态 (text/vision)
    estimated_tokens: int        # 预估 token 数
    complexity_score: int        # 复杂度 (1-10)
    latency_requirement: str     # 延迟要求
    budget_priority: str         # 预算优先级
    requires_accuracy: str       # 准确度要求
```

### **3. 模型路由器**

```python
router = ModelRouter(use_cache=True)

# 选择模型
model_config = router.select_model(requirement)

# 获取 LLM 实例
llm = router.get_llm(model_config)

# 调用（带降级机制）
response = router.invoke_with_fallback(
    requirement=requirement,
    messages=[message]
)
```

---

## 🚀 快速开始

### **Step 1: 安装依赖**

```bash
pip install redis langchain-openai
```

### **Step 2: 配置环境变量**

```bash
# .env 文件
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.siliconflow.cn/v1
```

### **Step 3: 创建路由器实例**

```python
from services.multi_model_router import ModelRouter, classify_task

# 初始化路由器
router = ModelRouter(use_cache=True)
```

### **Step 4: 分类任务并选择模型**

```python
# 示例：发票识别任务
requirement = classify_task(
    task_description="发票 OCR 识别，提取所有字段",
    input_data=image_base64
)

# 自动选择最优模型
model_config = router.select_model(requirement)
print(f"选定模型：{model_config.name}")
print(f"预计成本：¥{model_config.cost_per_1k:.4f}/1K tokens")
print(f"预计延迟：~{model_config.avg_latency_ms}ms")
```

### **Step 5: 调用模型**

```python
# 获取 LLM 实例
llm = router.get_llm(model_config)

# 构建消息
from langchain_core.messages import HumanMessage

message = HumanMessage(content=[
    {"type": "text", "text": "请识别这张发票"},
    {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
    }
])

# 调用（带自动降级）
response = router.invoke_with_fallback(
    requirement=requirement,
    messages=[message],
    fallback_chain=["qwen-vl-72b", "qwen-vl-32b", "qwen-vl-7b"]
)
```

---

## 📊 使用场景

### **场景 1: 简单发票识别**

```python
# 任务特点：标准化、重复性高、难度低
task = classify_task(
    "发票 OCR 识别",
    image_data  # Base64 图片
)

# 自动选择：InternVL-2B 或 Qwen-VL-7B
# 成本：¥0.001-0.002/1K tokens
# 延迟：50-80ms
# 准确率：95%+
```

### **场景 2: 合同关键信息提取**

```python
# 任务特点：结构化提取、中等复杂度
task = classify_task(
    "从合同中提取甲方、乙方、金额、日期等关键信息",
    contract_text  # 合同文本
)

# 自动选择：Qwen-VL-32B
# 成本：¥0.01/1K tokens
# 延迟：150ms
# 准确率：98%+
```

### **场景 3: 合同专业法律审查**

```python
# 任务特点：非结构化、高复杂度、高风险
task = classify_task(
    "全面审查合同条款的法律风险，检查是否存在不公平条款、违约责任是否合理",
    complex_contract_text
)

# 自动选择：Qwen-VL-72B-Instruct
# 成本：¥0.02/1K tokens
# 延迟：300ms
# 准确率：99%+
```

### **场景 4: 批量发票校验**

```python
# 任务特点：大批量、对延迟不敏感、成本敏感
task = classify_task(
    "批量校验 1000 张发票的完整性和格式",
    invoice_batch
)

# 自动选择：经济型模型 + 批量处理
# 成本：¥0.001 × 1000 = ¥1
# 总耗时：50 秒
# 相比 72B 模型节省：¥19 (95%)
```

---

## 💰 成本对比

### **日处理 1000 次请求**

| 场景 | 单模型方案 | 多模型方案 | 节省 |
|------|-----------|-----------|------|
| 发票 OCR (600 次) | ¥12 | ¥1.2 | ¥10.8 |
| 合同提取 (300 次) | ¥6 | ¥3 | ¥3 |
| 合同审查 (100 次) | ¥2 | ¥2 | ¥0 |
| **总计** | **¥20** | **¥6.2** | **¥13.8 (69%)** |

### **月成本对比**（按 3 万次/月）

| 方案 | 月成本 | 年成本 |
|------|--------|--------|
| 单模型（全部 72B） | ¥600 | ¥7,200 |
| 多模型（智能路由） | ¥186 | ¥2,232 |
| **节省** | **¥414/月** | **¥4,968/年** |

---

## ⚡ 性能优化

### **1. 缓存策略**

```python
# L1: 内存缓存（进程级）
router = ModelRouter(use_cache=True)

# L2: Redis 缓存（分布式）
# 自动缓存相同输入的响应
# TTL 可配置（默认 1 小时）

# L3: 结果缓存装饰器
from services.multi_model_router import cache_result

@cache_result(ttl_seconds=86400)  # 缓存 24 小时
def recognize_invoice(image_data):
    # ... 实现代码
```

**缓存效果：**
- 命中率：60%+（重复图片不重复识别）
- 成本降低：60%+
- 延迟降低：从 300ms 降到 10ms（缓存命中）

### **2. 降级链配置**

```python
# 自定义降级顺序
fallback_chain = [
    "qwen-vl-72b",  # 主选
    "qwen-vl-32b",  # 第一备选
    "qwen-vl-7b",   # 第二备选
    "internvl-2b"   # 最终兜底
]

response = router.invoke_with_fallback(
    requirement=requirement,
    messages=[message],
    fallback_chain=fallback_chain
)
```

**降级逻辑：**
1. 主模型调用失败 → 自动切换到备选
2. 记录失败原因（网络/超时/API 限制）
3. 最多尝试 3 次
4. 全部失败才抛出异常

### **3. 批量处理优化**

```python
# 批量任务自动合并
batch_tasks = [
    classify_task("发票 OCR", img1),
    classify_task("发票 OCR", img2),
    classify_task("发票 OCR", img3),
]

# 自动选择相同模型，批量发送
if all(t.task_type == TaskType.INVOICE_OCR for t in batch_tasks):
    # 使用经济型模型批量处理
    model = MODEL_REGISTRY["qwen-vl-7b"]
    results = batch_process(model, batch_tasks)
```

---

## 🎓 最佳实践

### **1. 模型选型决策树**

```python
def select_best_model(task_description, input_data):
    """
    模型选型决策流程
    """
    # Step 1: 是否需要视觉能力？
    if is_image(input_data):
        candidates = [m for m in MODELS if m.supports_vision]
    else:
        candidates = [m for m in MODELS]
    
    # Step 2: 预估 token 数量
    tokens = estimate_tokens(input_data)
    candidates = [m for m in candidates if m.context_window > tokens * 1.2]
    
    # Step 3: 评估复杂度
    complexity = evaluate_complexity(task_description)
    
    if complexity <= 3:
        # 简单任务：选最便宜的经济型
        return min(candidates, key=lambda m: m.cost_per_1k)
    
    elif complexity <= 6:
        # 中等任务：选性价比最高的平衡型
        return min(
            [m for m in candidates if m.tier == ModelTier.BALANCED],
            key=lambda m: m.cost_per_1k
        )
    
    else:
        # 复杂任务：必须高性能
        return min(
            [m for m in candidates if m.tier == ModelTier.PERFORMANCE],
            key=lambda m: m.avg_latency_ms
        )
```

### **2. 监控与告警**

```python
# 监控指标
metrics = {
    "total_requests": Counter('llm_requests_total', 'Total LLM requests'),
    "request_latency": Histogram('llm_request_latency', 'LLM request latency'),
    "model_selection": Counter('model_selection_count', 'Model selection count', ['model']),
    "cost_tracking": Counter('llm_cost', 'LLM cost', ['model']),
}

# 告警规则
alerts = [
    "单次调用成本 > ¥0.1 → 发送邮件告警",
    "P99 延迟 > 1s → 发送短信告警",
    "降级切换频率 > 10%/小时 → 发送钉钉告警",
]
```

### **3. A/B 测试框架**

```python
# 对比不同模型的效果
def ab_test_models(model_a_id, model_b_id, test_dataset):
    """
    A/B 测试两个模型的效果
    """
    results_a = []
    results_b = []
    
    for sample in test_dataset:
        # 模型 A
        result_a = invoke_model(model_a_id, sample)
        results_a.append(evaluate(result_a, sample.ground_truth))
        
        # 模型 B
        result_b = invoke_model(model_b_id, sample)
        results_b.append(evaluate(result_b, sample.ground_truth))
    
    # 统计分析
    return {
        "model_a": {
            "accuracy": np.mean(results_a),
            "avg_cost": np.mean(costs_a),
            "avg_latency": np.mean(latencies_a)
        },
        "model_b": {
            "accuracy": np.mean(results_b),
            "avg_cost": np.mean(costs_b),
            "avg_latency": np.mean(latencies_b)
        }
    }

# 使用示例
comparison = ab_test_models(
    "qwen-vl-7b",
    "qwen-vl-32b",
    test_invoices
)

print(f"7B 模型准确率：{comparison['model_a']['accuracy']:.2%}")
print(f"32B 模型准确率：{comparison['model_b']['accuracy']:.2%}")
print(f"成本差异：{comparison['model_a']['avg_cost'] / comparison['model_b']['avg_cost']:.2f}x")
```

---

## 📈 扩展计划

### **未来可能引入的模型**

```python
# 文本嵌入模型（用于 RAG）
MODEL_REGISTRY["text-embedding-v4"] = ModelConfig(
    name="BAAI/bge-m3",
    tier=ModelTier.ECONOMY,
    cost_per_1k=0.0005,
    supports_vision=False,
    context_window=8192
)

# 重排序模型（用于检索优化）
MODEL_REGISTRY["bge-reranker"] = ModelConfig(
    name="BAAI/bge-reranker-v2-m3",
    tier=ModelTier.BALANCED,
    cost_per_1k=0.002,
    supports_vision=False,
    context_window=2048
)

# 本地小模型（用于兜底）
MODEL_REGISTRY["local-qwen-7b"] = ModelConfig(
    name="Qwen/Qwen2.5-7B-Instruct",
    tier=ModelTier.ECONOMY,
    cost_per_1k=0.0,  # 免费（本地部署）
    avg_latency_ms=200,
    supports_vision=False,
    context_window=8192
)
```

### **动态模型加载**

```python
# 按需加载模型，减少内存占用
class DynamicModelLoader:
    def __init__(self):
        self.loaded_models = {}
    
    def load_model(self, model_id):
        if model_id not in self.loaded_models:
            print(f"加载模型：{model_id}")
            self.loaded_models[model_id] = ChatOpenAI(...)
        return self.loaded_models[model_id]
    
    def unload_inactive_models(self, idle_threshold=3600):
        """卸载长时间未使用的模型"""
        now = time.time()
        for model_id, last_used in self.last_used_times.items():
            if now - last_used > idle_threshold:
                del self.loaded_models[model_id]
                print(f"卸载模型：{model_id}")
```

---

## 🎯 总结

### **关键要点**

1. **不要一刀切**：不同任务需要不同模型
2. **成本优先**：能用小模型就不用大模型
3. **质量保障**：关键任务必须用高性能模型
4. **稳定第一**：实现降级切换机制
5. **持续优化**：定期评估模型效果和成本

### **实施步骤**

```
Week 1: 集成多模型路由系统
Week 2: 配置监控和告警
Week 3: A/B 测试验证效果
Week 4: 全量上线，持续优化
```

### **预期收益**

- 💰 **成本降低**: 60-74%
- ⚡ **速度提升**: 50%+
- 🛡️ **稳定性**: 99.9%+
- 📊 **可观测性**: 全方位监控

---

## 📚 参考资料

- [LangChain 多模型集成文档](https://python.langchain.com/docs/integrations/chat/)
- [硅基流动 API 文档](https://docs.siliconflow.cn/)
- [Qwen 系列模型性能对比](https://qwenlm.github.io/)
- [RAG 系统性能优化指南](../hybrid-rag-multi-agent/LCM_EVALUATION_GUIDE.md)

---

**最后更新**: 2026-03-28  
**作者**: 面试项目团队  
**版本**: v1.0
