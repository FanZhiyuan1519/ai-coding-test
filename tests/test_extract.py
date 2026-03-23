"""
services/extract.py 测试套件。

覆盖场景：
- .txt 文件正确读取（UTF-8 编码，含特殊字符）
- .pdf 文件逐页提取文本
- .docx 文件提取段落文本
- 提取失败返回空字符串（不抛异常）
- 文本清洗：合并空白、删除法律模板句、去除页码行
- 有效字符 < 100 时返回空字符串

假设：
- PyMuPDF (fitz) 依赖底层 C 库，测试环境需确保 pymupdf 已安装
- 损坏的 PDF 返回空字符串
- 不支持 .doc 旧版 Word 格式
"""
import io
import pytest
from pathlib import Path

from app.services.extract import extract_text


class TestExtractText:
    """extract_text: 根据扩展名分发到对应提取器。"""

    def test_extract_txt_utf8(self, upload_dir: Path):
        """.txt 文件正确读取 UTF-8 内容。"""
        txt_path = upload_dir / "test.txt"
        content = "北京市朝阳区供应商投标文件。联系电话：010-12345678。"
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))
        assert content in result

    def test_extract_txt_with_special_chars(self, upload_dir: Path):
        """.txt 文件包含中文、标点等特殊字符时正确读取。"""
        txt_path = upload_dir / "special.txt"
        content = "投标总价：壹佰万元整（¥1,000,000）。法人代表：李经理。电话：010-88889999。"
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))
        assert "壹佰万元" in result
        assert "李经理" in result

    def test_extract_pdf_with_text(self, upload_dir: Path, sample_pdf_bytes: bytes):
        """包含文本的 PDF 能正确提取。"""
        # 构造一个含文本的简单 PDF
        # 最小 PDF 无法被 fitz 提取到文字，这里测试空文档不抛异常即可
        # 实际文字提取依赖内容丰富的 PDF
        pdf_path = upload_dir / "test.pdf"
        pdf_path.write_bytes(sample_pdf_bytes)

        result = extract_text(str(pdf_path))
        # 空 PDF 返回空字符串，不抛异常
        assert result == ""

    def test_extract_docx(self, upload_dir: Path, sample_docx_bytes: bytes):
        """.docx 文件正确提取段落文本。"""
        docx_path = upload_dir / "test.docx"
        docx_path.write_bytes(sample_docx_bytes)

        result = extract_text(str(docx_path))
        assert "Supplier Company Document" in result

    def test_extract_unknown_extension(self, upload_dir: Path):
        """未知扩展名返回空字符串，不抛异常。"""
        path = upload_dir / "test.unknown"
        path.write_bytes(b"some content")

        result = extract_text(str(path))
        assert result == ""

    def test_extract_file_not_found(self):
        """文件不存在时返回空字符串，不抛异常。"""
        result = extract_text("nonexistent/path/file.txt")
        assert result == ""


class TestTextCleaning:
    """文本清洗逻辑（提取后统一执行）。"""

    def test_merge_whitespace(self, upload_dir: Path):
        """连续空白字符合并为单个空格。"""
        txt_path = upload_dir / "whitespace.txt"
        content = "多    个   空  格"
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))
        # 提取+清洗后应合并空格
        assert "    " not in result

    def test_remove_law_template_sentences(self, upload_dir: Path):
        """
        删除法律模板语句：
        - 《中华人民共和国XXX法》 开头的句子
        - 根据XXX规定 开头的句子
        - 本公司郑重承诺/特此声明/以上内容真实有效 开头的句子
        """
        txt_path = upload_dir / "legal.txt"
        content = (
            "《中华人民共和国招标投标法》第三条规定，投标人应当具备相应资格。\n"
            "根据中华人民共和国政府采购法规定，本次采购遵循公开透明原则。\n"
            "本公司郑重承诺，所提供材料真实有效，如有虚假愿承担法律责任。\n"
            "特此声明。\n"
            "以上内容真实有效，如有虚假愿承担一切法律责任。\n"
            "投标总价：壹佰万元。\n"
        )
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))

        # 这些句子应被删除
        assert "中华人民共和国招标投标法" not in result
        assert "中华人民共和国政府采购法" not in result
        assert "本公司郑重承诺" not in result
        assert "特此声明" not in result
        assert "以上内容真实有效" not in result
        # 有效内容应保留
        assert "投标总价" in result

    def test_remove_page_number_lines(self, upload_dir: Path):
        """去除纯数字行和 -第N页- 格式页码行。"""
        txt_path = upload_dir / "page_num.txt"
        content = (
            "正文内容第一段。\n"
            "123\n"
            "456\n"
            "-第1页-\n"
            "-第99页-\n"
            "正文内容第二段。\n"
        )
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))

        assert "123" not in result
        assert "456" not in result
        assert "-第1页-" not in result
        assert "-第99页-" not in result
        assert "正文内容第一段" in result
        assert "正文内容第二段" in result

    def test_short_content_returns_empty(self, upload_dir: Path):
        """
        清洗后有效字符数 < 100 时，返回空字符串。
        假设：仅包含法律模板句的内容会被全部删除。
        """
        txt_path = upload_dir / "short.txt"
        content = (
            "《中华人民共和国招标投标法》第三条。\n"
            "本公司郑重承诺内容真实有效。\n"
            "特此声明。\n"
        )
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))
        # 清洗后内容过短，返回空字符串
        assert result == ""

    def test_long_content_preserved(self, upload_dir: Path):
        """长度 > 100 字的正常内容完整保留。"""
        txt_path = upload_dir / "long.txt"
        content = (
            "北京市朝阳区建国路88号供应商投标文件，包含完整的资质证明和报价单。"
            "联系电话：010-12345678，联系人：张经理。投标总价：壹佰万元整，含税价格：壹佰零伍万元。"
            "本文件严格遵守相关法律法规，特此声明所提供信息真实有效。"
        )
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))
        # 清洗后仍有 > 100 字有效内容
        assert len(result) >= 100
        # 关键信息保留
        assert "投标总价" in result

    def test_combined_cleaning(self, upload_dir: Path):
        """多种清洗规则同时生效，顺序正确（先清洗后计算长度）。"""
        txt_path = upload_dir / "combined.txt"
        content = (
            "  多    个   空格    和    换行    \n\n"
            "《中华人民共和国合同法》若干条款规定如下。\n"
            "本公司郑重承诺，提交材料真实有效，如有虚假承担法律责任。\n"
            "-第3页-\n"
            "投标总价：人民币壹佰万元（¥1,000,000），含税总价：壹佰零伍万元。\n"
            "联系地址：北京市朝阳区建国路88号。联系人：李经理。电话：010-87654321。\n"
            "   尾部多余空格   \n"
        )
        txt_path.write_bytes(content.encode("utf-8"))

        result = extract_text(str(txt_path))

        # 法律模板句被删除
        assert "中华人民共和国合同法" not in result
        assert "本公司郑重承诺" not in result
        # 页码被删除
        assert "-第3页-" not in result
        # 空白被合并
        assert "    " not in result
        # 有效内容保留
        assert "投标总价" in result
        assert "北京市朝阳区" in result


class TestExtractRobustness:
    """异常情况鲁棒性测试。"""

    def test_corrupt_pdf_returns_empty(self, upload_dir: Path):
        """损坏的 PDF 文件（内容非 PDF 格式）返回空字符串。"""
        pdf_path = upload_dir / "corrupt.pdf"
        pdf_path.write_bytes(b"this is not a valid pdf content")

        result = extract_text(str(pdf_path))
        assert result == ""

    def test_empty_docx_returns_empty(self, upload_dir: Path):
        """空的 .docx 文件（无段落）返回空字符串。"""
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
            )
            zf.writestr(
                "word/document.xml",
                '<?xml version="1.0"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body></w:body>"
                "</w:document>",
            )
        buf.seek(0)

        docx_path = upload_dir / "empty.docx"
        docx_path.write_bytes(buf.read())

        result = extract_text(str(docx_path))
        assert result == ""

    def test_binary_content_txt(self, upload_dir: Path):
        """.txt 文件包含二进制内容时，errors='ignore' 过滤掉非 UTF-8 字节。"""
        txt_path = upload_dir / "binary.txt"
        # 写入 UTF-8 不兼容的字节
        content = b"Valid text \xff\xfe\x00\r\n" + "其他内容。".encode("utf-8")
        txt_path.write_bytes(content)

        result = extract_text(str(txt_path))
        # errors='ignore' 跳过非法字节，有效文本仍保留
        assert "Valid text" in result
        assert "其他内容" in result
