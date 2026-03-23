from __future__ import annotations

import re
from typing import Optional
from app.schemas.schemas import RiskLevel


def extract_key_info_regex(text: str) -> dict[str, Optional[str]]:
    """正则提取关键信息"""
    patterns = {
        '经营地址': [r'经营地址[：:]\s*(.+?)(?:\n|$)', r'经营场所[：:]\s*(.+?)(?:\n|$)', 
                   r'公司地址[：:]\s*(.+?)(?:\n|$)', r'注册地址[：:]\s*(.+?)(?:\n|$)', 
                   r'通讯地址[：:]\s*(.+?)(?:\n|$)'],
        '联系电话': [r'联系电话[：:]\s*(.+?)(?:\n|$)', r'联系方式[：:]\s*(.+?)(?:\n|$)',
                    r'电话[：:]\s*(.+?)(?:\n|$)', r'Tel[：:]\s*(.+?)(?:\n|$)'],
        '社会信用代码': [r'统一社会信用代码[：:]\s*(.+?)(?:\n|$)', r'社会信用代码[：:]\s*(.+?)(?:\n|$)',
                       r'信用代码[：:]\s*(.+?)(?:\n|$)'],
        '法人代表': [r'法定代表人[：:]\s*(.+?)(?:\n|$)', r'法人代表[：:]\s*(.+?)(?:\n|$)',
                    r'法人[：:]\s*(.+?)(?:\n|$)'],
        '委托人姓名': [r'授权委托人[：:]\s*(.+?)(?:\n|$)', r'委托人[：:]\s*(.+?)(?:\n|$)',
                      r'代理人[：:]\s*(.+?)(?:\n|$)'],
    }
    
    result = {}
    for field, field_patterns in patterns.items():
        value = None
        for pattern in field_patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                break
        result[field] = value
    
    return result


def check_key_info(info_a: dict, info_b: dict) -> list[str]:
    """比较两份文件的关键信息，返回匹配的字段列表"""
    matches = []
    for field in info_a:
        if info_a[field] and info_b.get(field):
            if info_a[field].strip() == info_b[field].strip():
                matches.append(field)
    return matches


def check_similarity(text_a: str, text_b: str) -> tuple[float, int]:
    """计算文本相似度，返回 (similarity_ratio, lcs_length)"""
    sentences_a = [s.strip() for s in re.split(r'[。！？\n]', text_a) if len(s.strip()) >= 4]
    sentences_b = [s.strip() for s in re.split(r'[。！？\n]', text_b) if len(s.strip()) >= 4]
    
    matched_a = set()
    matched_b = set()
    for i, sa in enumerate(sentences_a):
        for j, sb in enumerate(sentences_b):
            if i not in matched_a and j not in matched_b:
                similarity = _bigram_jaccard(sa, sb)
                if similarity >= 0.8:
                    matched_a.add(i)
                    matched_b.add(j)
    
    total_similar_chars = sum(len(sentences_a[i]) for i in matched_a)
    avg_len = (len(text_a) + len(text_b)) / 2
    similarity_ratio = round((total_similar_chars / avg_len * 100) if avg_len > 0 else 0, 1)
    similarity_ratio = min(100.0, similarity_ratio)
    
    lcs_length = _lcs_length(text_a, text_b)
    
    return similarity_ratio, lcs_length


def _bigram_jaccard(text_a: str, text_b: str) -> float:
    """计算 bigram Jaccard 相似度"""
    def get_bigrams(text):
        return set(text[i:i+2] for i in range(len(text)-1))
    
    bigrams_a = get_bigrams(text_a)
    bigrams_b = get_bigrams(text_b)
    
    if not bigrams_a or not bigrams_b:
        return 0.0
    
    intersection = len(bigrams_a & bigrams_b)
    union = len(bigrams_a | bigrams_b)
    
    return intersection / union if union > 0 else 0.0


def _lcs_length(text_a: str, text_b: str) -> int:
    """计算最长公共连续子串长度"""
    m, n = len(text_a), len(text_b)
    if m == 0 or n == 0:
        return 0
    
    dp = [[0] * (n + 1) for _ in range(2)]
    max_len = 0
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if text_a[i-1] == text_b[j-1]:
                dp[i % 2][j] = dp[(i-1) % 2][j-1] + 1
                max_len = max(max_len, dp[i % 2][j])
            else:
                dp[i % 2][j] = 0
    
    return max_len


def check_price(text_a: str, text_b: str) -> tuple[Optional[float], dict[str, Optional[float]]]:
    """提取报价并计算相关系数"""
    price_a = _extract_prices(text_a)
    price_b = _extract_prices(text_b)
    
    price_values = {
        'text_a': price_a[0] if price_a else None,
        'text_b': price_b[0] if price_b else None,
    }
    
    correlation = None
    if len(price_a) >= 3 and len(price_b) >= 3:
        correlation = _pearson_correlation(price_a[:10], price_b[:10])
    
    return correlation, price_values


def _extract_prices(text: str) -> list[float]:
    """提取报价数值"""
    patterns = [
        r'(?:投标总价|报价|含税总价|合同总价)[：:\s]*([\d,.]+)\s*(万元|万|元)?',
    ]
    
    prices = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            try:
                value_str = m[0]
                value = float(value_str.replace(',', ''))
                if m[1] in ('万元', '万'):
                    value *= 10000
                if value > 100:
                    prices.append(value)
            except (ValueError, IndexError):
                pass
    
    return prices


def _pearson_correlation(x: list, y: list) -> Optional[float]:
    """计算皮尔逊相关系数"""
    n = min(len(x), len(y))
    if n < 3:
        return None
    
    x = x[:n]
    y = y[:n]
    
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denominator_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    denominator_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
    
    if denominator_x == 0 or denominator_y == 0:
        return None
    
    return numerator / (denominator_x * denominator_y)


def assess_risk(
    key_info_match: list[str],
    similarity_ratio: float,
    lcs_length: int,
    price_correlation: Optional[float]
) -> RiskLevel:
    """风险等级判定"""
    if key_info_match:
        return RiskLevel.high
    if similarity_ratio >= 60 or lcs_length >= 100:
        return RiskLevel.high
    if price_correlation is not None and price_correlation >= 0.99:
        return RiskLevel.high
    if similarity_ratio >= 15:
        return RiskLevel.medium
    return RiskLevel.low
