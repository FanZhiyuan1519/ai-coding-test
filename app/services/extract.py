import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def extract_text(stored_path: str) -> str:
    """从文件提取文本"""
    import fitz
    import docx
    
    ext = stored_path.lower().split('.')[-1]
    
    try:
        if ext == 'txt':
            with open(stored_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        elif ext == 'pdf':
            text = ''
            doc = fitz.open(stored_path)
            for page in doc:
                text += page.get_text()
            doc.close()
        elif ext == 'docx':
            doc = docx.Document(stored_path)
            text = '\n'.join([p.text for p in doc.paragraphs])
        else:
            return ''
    except Exception as e:
        logger.warning(f"提取文件失败 {stored_path}: {e}")
        return ''
    
    text = clean_text(text)
    if len(text.strip()) < 10:
        logger.warning(f"提取文本过少 {stored_path}: {len(text)} 字符")
        return ''
    
    return text


def clean_text(text: str) -> str:
    """文本清洗"""
    patterns_to_remove = [
        r'《中华人民共和国.*?》[^\n。]*',
        r'根据.*?规定[^\n。]*',
        r'^本公司郑重承诺.*$',
        r'^特此声明.*$',
        r'^以上内容真实有效.*$',
        r'^\d+$',
        r'^-第\d+页-$',
    ]
    
    for pattern in patterns_to_remove:
        text = re.sub(pattern, '', text, flags=re.MULTILINE)
    
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()
