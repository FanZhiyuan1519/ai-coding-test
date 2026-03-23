import json
import logging
from typing import Optional
import requests
from app.core.config import get_settings
from app.services.compare import extract_key_info_regex, RiskLevel

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        settings = get_settings()
        self.model_url = settings.AI_MODEL_URL
        self.model_name = settings.AI_MODEL_ID
        self.api_key = settings.AI_API_KEY

    def chat(self, messages: list, temperature: float = 0.7, max_tokens: int = 2000) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else ""
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            response = requests.post(
                self.model_url,
                json=payload,
                headers=headers,
                timeout=120
            )

            if response.status_code != 200:
                raise RuntimeError(f"模型调用失败: {response.status_code} - {response.text}")

            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            raise RuntimeError("模型调用超时")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("模型服务连接失败")


def get_llm_client() -> LLMClient:
    return LLMClient()


def extract_key_info_ai(text: str) -> dict:
    """
    使用 AI 补充提取关键信息
    触发条件：正则提取的非空字段数 < 3
    降级实现（AI_ENABLED=false）：直接返回正则结果
    """
    settings = get_settings()
    if not settings.AI_ENABLED:
        return extract_key_info_regex(text)

    regex_result = extract_key_info_regex(text)
    non_none_count = sum(1 for v in regex_result.values() if v is not None)

    if non_none_count >= 3:
        return regex_result

    client = get_llm_client()

    prompt = f"""从以下投标文件中提取关键信息，以JSON格式返回。

需要提取的字段：
- 经营地址：公司经营场所地址
- 联系电话：电话号码或手机号
- 社会信用代码：18位统一社会信用代码
- 法人代表：法定代表人姓名
- 委托人姓名：授权委托人姓名

如果某字段无法识别，设为null，不要推测。

投标文件内容：
{text[:5000]}

输出格式（严格JSON）：
{{
  "经营地址": "地址或null",
  "联系电话": "电话或null",
  "社会信用代码": "代码或null",
  "法人代表": "姓名或null",
  "委托人姓名": "姓名或null"
}}

只返回JSON，不要有其他内容。"""

    try:
        messages = [{"role": "user", "content": prompt}]
        response = client.chat(messages, temperature=0.3)

        result = _parse_json_response(response)
        if result:
            for key in regex_result:
                if regex_result[key] is not None and result.get(key) is None:
                    result[key] = regex_result[key]
            return result
    except Exception as e:
        logger.warning(f"AI提取关键信息失败，降级为正则结果: {e}")

    return regex_result


def generate_risk_reason(
    supplier_a: str,
    supplier_b: str,
    level: RiskLevel,
    detail
) -> str:
    """
    生成风险原因描述
    触发条件：level 为 high 或 medium
    降级实现（AI_ENABLED=false）：规则拼接模板字符串
    """
    settings = get_settings()
    if level == RiskLevel.low:
        return "未检测到明显异常"

    if not settings.AI_ENABLED:
        return _build_fallback_reason(supplier_a, supplier_b, detail)

    client = get_llm_client()

    key_info_match = getattr(detail, 'key_info_match', []) or []
    similarity_ratio = getattr(detail, 'similarity_ratio', 0) or 0
    lcs_length = getattr(detail, 'lcs_length', 0) or 0
    price_correlation = getattr(detail, 'price_correlation', None)
    price_values = getattr(detail, 'price_values', {}) or {}

    prompt = f"""你是一个招投标审计专家。根据以下检测数据，生成一段客观的中文风险描述。

检测数据：
- 投标单位A：{supplier_a}
- 投标单位B：{supplier_b}
- 风险等级：{'高风险' if level == RiskLevel.high else '中风险'}
- 雷同比例：{similarity_ratio:.1f}%
- 最长连续相同段落：{lcs_length}字
- 报价相关系数：{price_correlation if price_correlation is not None else '数据不足'}
- 关键信息匹配字段：{', '.join(key_info_match) if key_info_match else '无'}

要求：
1. 语气客观，不做最终定性判断，不写"确定围标"等结论
2. 输出 ≤ 150字
3. 突出关键异常点，供评审专家参考
4. 只返回描述文本，不要有其他内容。"""

    try:
        messages = [{"role": "user", "content": prompt}]
        response = client.chat(messages, temperature=0.5, max_tokens=200)
        if response:
            return response
    except Exception as e:
        logger.warning(f"AI生成风险原因失败，降级为模板: {e}")

    return _build_fallback_reason(supplier_a, supplier_b, detail)


def _build_fallback_reason(supplier_a: str, supplier_b: str, detail) -> str:
    """降级实现：规则拼接模板字符串"""
    parts = []

    key_info_match = getattr(detail, 'key_info_match', []) or []
    similarity_ratio = getattr(detail, 'similarity_ratio', 0) or 0
    lcs_length = getattr(detail, 'lcs_length', 0) or 0
    price_correlation = getattr(detail, 'price_correlation', None)

    if key_info_match:
        parts.append(f"关键信息字段 {'/'.join(key_info_match)} 完全一致")

    if similarity_ratio:
        parts.append(f"文件雷同比例 {similarity_ratio:.1f}%")

    if lcs_length >= 100:
        parts.append(f"最长连续相同段落 {lcs_length} 字")

    if price_correlation is not None:
        parts.append(f"报价相关系数 {price_correlation:.3f}")

    if parts:
        return "；".join(parts) + "。"
    return "检测到一定相似性，建议进一步核查。"


def _parse_json_response(response: str) -> Optional[dict]:
    """解析 JSON 响应"""
    try:
        json_match = _extract_json(response)
        if json_match:
            return json.loads(json_match)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败: {e}")
    return None


def _extract_json(text: str) -> Optional[str]:
    """从文本中提取 JSON"""
    import re
    json_patterns = [
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
    ]

    for pattern in json_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip() if '```' in pattern else match.group()

    if text.strip().startswith('{') and text.strip().endswith('}'):
        return text.strip()

    return None
