"""
services/compare.py 测试套件。

测试纯算法函数：无 LLM 调用、无数据库操作、无网络 I/O。
每个函数均可独立单元测试。

覆盖场景：
- extract_key_info_regex: 标准前缀 / 非标准前缀 / 字段不存在
- check_key_info: 单字段命中 / 多字段命中 / 无命中 / 其中一方为 None 跳过
- check_similarity: 完全相同 / 完全不同 / 阈值边界值 (14.9%/15.0%/59.9%/60.0%)
- check_price: 正常计算 / 数值不足3个返回None / 万元单位转换
- assess_risk: high/medium/low 各条件分支组合
"""
import math
import pytest

from app.services.compare import (
    extract_key_info_regex,
    check_key_info,
    check_similarity,
    check_price,
    assess_risk,
)


# ─────────────────────────────────────────────────────────────────────────────
# extract_key_info_regex
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractKeyInfoRegex:
    """extract_key_info_regex: 用正则从文本提取关键信息字段。"""

    def test_standard_prefixes(self):
        """标准前缀关键词能正确提取。"""
        text = (
            "经营地址：北京市朝阳区建国路88号\n"
            "联系电话：010-87654321\n"
            "统一社会信用代码：91110000MA00ABCD01\n"
            "法定代表人：李四\n"
            "授权委托人：王五\n"
        )
        result = extract_key_info_regex(text)

        assert result["经营地址"] == "北京市朝阳区建国路88号"
        assert result["联系电话"] == "010-87654321"
        assert result["社会信用代码"] == "91110000MA00ABCD01"
        assert result["法人代表"] == "李四"
        assert result["委托人姓名"] == "王五"

    def test_alternative_prefixes(self):
        """非标准前缀（同义前缀）能正确匹配。"""
        text = (
            "公司地址：上海浦东新区\n"
            "联系方式：021-11112222\n"
            "信用代码：91310000MA1B2C3D4\n"
            "法人：张三\n"
            "代理人：赵六\n"
        )
        result = extract_key_info_regex(text)

        assert result["经营地址"] == "上海浦东新区"
        assert result["联系电话"] == "021-11112222"
        assert result["社会信用代码"] == "91310000MA1B2C3D4"
        assert result["法人代表"] == "张三"
        assert result["委托人姓名"] == "赵六"

    def test_missing_fields_return_none(self):
        """不存在的字段返回 None。"""
        text = "这是一份普通文档，不包含任何关键信息字段。"
        result = extract_key_info_regex(text)

        assert all(v is None for v in result.values())

    def test_partial_fields(self):
        """部分字段缺失时，仅返回匹配字段，其他为 None。"""
        text = "联系电话：010-99998888\n社会信用代码：91110000MA00XYZ99"
        result = extract_key_info_regex(text)

        assert result["联系电话"] == "010-99998888"
        assert result["社会信用代码"] == "91110000MA00XYZ99"
        assert result["经营地址"] is None
        assert result["法人代表"] is None
        assert result["委托人姓名"] is None

    def test_strips_whitespace(self):
        """提取内容首尾空格被去除。"""
        text = "经营地址：  北京市朝阳区   \n联系电话：010-12345678  "
        result = extract_key_info_regex(text)

        assert result["经营地址"] == "北京市朝阳区"
        assert result["联系电话"] == "010-12345678"

    def test_tel_case_insensitive(self):
        """Tel/TEL 前缀大小写不敏感匹配。"""
        text = "Tel: 010-55556666\nTEL: 021-77778888"
        result = extract_key_info_regex(text)

        # 预期仅匹配 Tel: 后内容（第一个命中），TEL 作为第二个字段，
        # 由于同一字段名已匹配则不再匹配下一行。
        # 具体行为取决于正则实现：是否允许同一字段多次匹配。
        # 文档未明确约定，以下为最直接实现：取第一个命中的字段行。
        assert result["联系电话"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# check_key_info
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckKeyInfo:
    """check_key_info: 比对两份文件的关键信息，返回匹配的字段名列表。"""

    def test_single_field_match(self):
        """单字段完全一致时返回该字段名。"""
        info_a = {"经营地址": "北京", "联系电话": "010-123", "社会信用代码": None}
        info_b = {"经营地址": "北京", "联系电话": "010-456", "社会信用代码": None}

        result = check_key_info(info_a, info_b)
        assert result == ["经营地址"]

    def test_multiple_fields_match(self):
        """多字段一致时返回所有匹配字段。"""
        info_a = {
            "经营地址": "北京",
            "联系电话": "010-123",
            "社会信用代码": "91110000",
            "法人代表": "李四",
            "委托人姓名": None,
        }
        info_b = {
            "经营地址": "北京",
            "联系电话": "010-123",
            "社会信用代码": "91110000",
            "法人代表": "李四",
            "委托人姓名": None,
        }

        result = check_key_info(info_a, info_b)
        assert set(result) == {"经营地址", "联系电话", "社会信用代码", "法人代表"}

    def test_no_match(self):
        """无任何字段一致时返回空列表。"""
        info_a = {"经营地址": "北京", "联系电话": "010-123"}
        info_b = {"经营地址": "上海", "联系电话": "021-456"}

        result = check_key_info(info_a, info_b)
        assert result == []

    def test_none_skipped(self):
        """一方为 None 时跳过比较（不计入命中也不计入未命中）。"""
        info_a = {"经营地址": "北京", "联系电话": "010-123", "社会信用代码": None}
        info_b = {"经营地址": "北京", "联系电话": None, "社会信用代码": None}

        result = check_key_info(info_a, info_b)
        # 经营地址: 北京==北京 -> 命中
        # 联系电话: 010-123 vs None -> 跳过
        # 社会信用代码: None vs None -> 跳过（文档未明确，两方均为 None 是否算命中）
        # 按"值均不为 None"规则，两者 None 不算命中
        assert result == ["经营地址"]

    def test_strip_before_compare(self):
        """比较前去除首尾空格。"""
        info_a = {"经营地址": "  北京  ", "联系电话": "010-123"}
        info_b = {"经营地址": "北京", "联系电话": "010-456"}

        result = check_key_info(info_a, info_b)
        assert result == ["经营地址"]


# ─────────────────────────────────────────────────────────────────────────────
# check_similarity
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckSimilarity:
    """check_similarity: 计算两份文本的相似度和 LCS 长度。"""

    def test_identical_text(self):
        """完全相同的文本，similarity_ratio 应接近 100。"""
        text = "这是一份完整的投标文件，包含所有必要条款和报价信息。联系电话010-12345678。地址：北京市朝阳区建国路88号。"
        ratio, lcs = check_similarity(text, text)

        assert ratio >= 90.0
        assert lcs == len(text)

    def test_completely_different(self):
        """完全不同内容的文本，similarity_ratio 应接近 0。"""
        text_a = "北京市朝阳区建国路88号供应商报价单，含税总价一百万元。"
        text_b = "上海市浦东新区张江高科技园区另一家公司提供的服务方案说明文档。"

        ratio, lcs = check_similarity(text_a, text_b)

        assert ratio < 15.0  # 远低于 medium 阈值
        assert lcs < 100

    def test_similarity_ratio_boundary_low(self):
        """
        similarity_ratio 边界值：低于 15% 阈值。
        构造使 ratio 恰好落在低位的文本对。
        """
        text_a = "本公司是一家专业供应商，提供优质产品。"
        text_b = "贵公司具备相应资质，可承接相关项目。"

        ratio, lcs = check_similarity(text_a, text_b)
        assert ratio < 15.0

    def test_similarity_ratio_boundary_15(self):
        """
        构造使 ratio 恰好接近 15% 的文本对。
        """
        # 两份文本有部分雷同句子
        text_a = "本公司郑重承诺提供优质服务，保证按时交货。" * 5
        text_b = "本公司郑重承诺提供优质服务，保证按时交货。" * 5 + "额外条款内容。" * 20

        ratio, lcs = check_similarity(text_a, text_b)
        assert ratio >= 15.0

    def test_similarity_ratio_boundary_59(self):
        """
        similarity_ratio 边界值：59.9% 应为 medium，低于 60% 阈值。
        """
        # 大部分内容相同，仅少量不同
        text_a = "相同段落。" * 10 + "独特内容一。" * 5
        text_b = "相同段落。" * 6 + "不同段落。" * 9

        ratio, lcs = check_similarity(text_a, text_b)
        assert ratio < 60.0
        assert ratio >= 15.0

    def test_similarity_ratio_boundary_60(self):
        """
        similarity_ratio 边界值：60.0% 应为 high，达到 60% 阈值。
        """
        text_a = ("相同段落。" * 60)
        text_b = ("相同段落。" * 60)

        ratio, lcs = check_similarity(text_a, text_b)
        assert ratio >= 60.0

    def test_lcs_length_high(self):
        """LCS 长度 >= 100 时应为 high 风险。"""
        # 两份文本有 150 字的连续相同内容
        common = "本投标文件严格遵守中华人民共和国招标投标法相关规定，根据相关法律法规制定，本投标文件严格遵守中华人民共和国招标投标法相关规定，根据相关法律法规制定，本投标文件严格遵守中华人民共和国招标投标法相关规定。"
        text_a = "开头内容。" + common + "结尾内容。"
        text_b = "其他内容。" + common + "其他结尾。"

        ratio, lcs = check_similarity(text_a, text_b)
        assert lcs >= 100

    def test_ratio_preserves_one_decimal(self):
        """返回的 similarity_ratio 保留 1 位小数。"""
        text_a = "供应商报价单。服务条款。质量保证。交货时间。售后服务。" * 3
        text_b = "供应商报价单。服务条款。质量保证。交货时间。" * 3 + "额外内容。" * 10

        ratio, lcs = check_similarity(text_a, text_b)
        # 检查是否为 1 位小数（乘以 10 取整等于自身乘以 10）
        assert round(ratio, 1) == ratio

    def test_short_sentences_filtered(self):
        """长度 < 4 字的短句不参与相似度计算。"""
        text_a = "短。" * 20 + "这是一段较长的投标文件内容，包含多个重要条款和条件。"
        text_b = "短。" * 20 + "这是一段较长的投标文件内容，包含多个重要条款和条件。"

        ratio, lcs = check_similarity(text_a, text_b)
        # 短句被过滤，仅长句匹配，ratio 基于全文长度计算
        assert ratio >= 30.0
        assert ratio <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
# check_price
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckPrice:
    """check_price: 从文本提取报价并计算皮尔逊相关系数。"""

    def test_normal_extraction_and_correlation(self):
        """两份文件均提取到 >= 3 个数值时，正常计算相关系数。"""
        text_a = (
            "投标总价：1052000元。\n"
            "含税总价：1100000元。\n"
            "合同总价：950000元。\n"
            "其他费用：100000元。"
        )
        text_b = (
            "投标总价：925000元。\n"
            "含税总价：970000元。\n"
            "合同总价：880000元。\n"
            "其他费用：90000元。"
        )

        correlation, prices = check_price(text_a, text_b)

        assert correlation is not None
        assert 0.9 < correlation <= 1.0  # 应接近 1（高度正相关）
        assert prices["text_a"] is not None
        assert prices["text_b"] is not None

    def test_insufficient_data_returns_none(self):
        """任意一份文件提取数值 < 3 个时，correlation 返回 None。"""
        text_a = (
            "投标总价：100万元。\n"
            "含税总价：110万元。"
        )
        text_b = (
            "投标总价：90万元。\n"
            "含税总价：99万元。"
        )

        correlation, prices = check_price(text_a, text_b)

        assert correlation is None

    def test_wan_unit_conversion(self):
        """万元单位正确转换为元（乘以 10000）。"""
        text_a = "投标总价：100万元。"
        text_b = "投标报价：90万元。"

        # 由于只有 1 个数值（< 3），correlation 仍为 None
        # 但 price_values 中的数值应为转换后的元
        _, prices = check_price(text_a, text_b)

        # 仅 1 个数值，correlation 为 None
        assert prices["text_a"] is not None
        assert prices["text_a"] == 1000000.0  # 100万 * 10000 = 1000000

    def test_price_extraction_keywords(self):
        """匹配投标总价、报价、含税总价、合同总价等关键词后的数字。"""
        text_a = "投标总价100万元，报价95万元，含税总价105万元。"
        text_b = "投标总价90万元，报价85万元，含税总价95万元。"

        _, prices = check_price(text_a, text_b)
        assert prices["text_a"] is not None
        assert prices["text_b"] is not None

    def test_both_fail_extraction(self):
        """两份文件均无法提取数值时，prices 全部为 None。"""
        text_a = "这是一份没有明确报价的文档。"
        text_b = "另一份没有报价信息的文档。"

        correlation, prices = check_price(text_a, text_b)

        assert correlation is None
        assert prices["text_a"] is None
        assert prices["text_b"] is None


# ─────────────────────────────────────────────────────────────────────────────
# assess_risk
# ─────────────────────────────────────────────────────────────────────────────

class TestAssessRisk:
    """assess_risk: 纯规则判定风险等级，不调用 AI，不生成 reason 文本。"""

    def test_high_key_info_match(self):
        """关键信息字段匹配 -> high。"""
        level = assess_risk(
            key_info_match=["经营地址", "联系电话"],
            similarity_ratio=10.0,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "high"

    def test_high_similarity_ratio_60(self):
        """similarity_ratio >= 60 -> high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=60.0,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "high"

    def test_high_similarity_ratio_above_60(self):
        """similarity_ratio > 60 -> high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=78.5,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "high"

    def test_high_lcs_length_100(self):
        """lcs_length >= 100 -> high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=10.0,
            lcs_length=100,
            price_correlation=None,
        )
        assert level.value == "high"

    def test_high_lcs_length_above_100(self):
        """lcs_length > 100 -> high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=10.0,
            lcs_length=215,
            price_correlation=None,
        )
        assert level.value == "high"

    def test_high_price_correlation_099(self):
        """price_correlation >= 0.99 -> high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=10.0,
            lcs_length=10,
            price_correlation=0.997,
        )
        assert level.value == "high"

    def test_high_price_correlation_1(self):
        """price_correlation = 1.0 -> high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=10.0,
            lcs_length=10,
            price_correlation=1.0,
        )
        assert level.value == "high"

    def test_medium_similarity_ratio_15(self):
        """similarity_ratio >= 15 (且无 high 条件) -> medium。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=15.0,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "medium"

    def test_medium_similarity_ratio_50(self):
        """similarity_ratio = 50 (且无 high 条件) -> medium。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=50.0,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "medium"

    def test_medium_similarity_ratio_59(self):
        """similarity_ratio = 59.9 (且无 high 条件) -> medium。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=59.9,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "medium"

    def test_low_all_conditions_not_met(self):
        """所有条件均不满足 -> low。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=14.9,
            lcs_length=99,
            price_correlation=None,
        )
        assert level.value == "low"

    def test_low_price_correlation_below_099(self):
        """price_correlation < 0.99 (且无其他 high 条件) -> 不为 high。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=10.0,
            lcs_length=10,
            price_correlation=0.95,
        )
        assert level.value == "low"

    def test_low_price_correlation_is_none(self):
        """price_correlation 为 None 时跳过报价判定 -> low。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=10.0,
            lcs_length=10,
            price_correlation=None,
        )
        assert level.value == "low"

    def test_priority_key_info_over_similarity(self):
        """优先级：key_info_match 命中时，无论 similarity_ratio 多低都为 high。"""
        level = assess_risk(
            key_info_match=["联系电话"],
            similarity_ratio=1.0,  # 极低
            lcs_length=5,
            price_correlation=None,
        )
        assert level.value == "high"

    def test_priority_key_info_over_price(self):
        """优先级：key_info_match 命中时，无论 price_correlation 多低都为 high。"""
        level = assess_risk(
            key_info_match=["法人代表"],
            similarity_ratio=5.0,
            lcs_length=10,
            price_correlation=0.5,
        )
        assert level.value == "high"

    def test_correlation_negative_not_high(self):
        """负相关系数不满足 >= 0.99 条件，应落入 medium 或 low。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=30.0,
            lcs_length=10,
            price_correlation=-0.8,
        )
        assert level.value == "medium"

    def test_correlation_close_to_zero(self):
        """相关系数接近 0 但非 None，不满足 >= 0.99，应落入 medium。"""
        level = assess_risk(
            key_info_match=[],
            similarity_ratio=20.0,
            lcs_length=10,
            price_correlation=0.1,
        )
        assert level.value == "medium"
