#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将 Word 文档转换为 PDF
使用 Windows Word COM 接口
"""

import os
import sys
from pathlib import Path


def convert_word_to_pdf(word_path: str, pdf_path: str = None):
    """使用 Word COM 接口将 docx 转换为 pdf"""
    word_path = Path(word_path).resolve()
    
    if not word_path.exists():
        print(f'错误：找不到文件 {word_path}')
        return False
    
    if pdf_path is None:
        pdf_path = word_path.with_suffix('.pdf')
    else:
        pdf_path = Path(pdf_path).resolve()
    
    try:
        # 尝试使用 win32com
        import win32com.client
        
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        
        # 打开文档
        doc = word.Documents.Open(str(word_path))
        
        # 保存为 PDF (17 = wdFormatPDF)
        doc.SaveAs2(str(pdf_path), FileFormat=17)
        doc.Close()
        word.Quit()
        
        print(f'PDF 文档已生成：{pdf_path}')
        return True
        
    except ImportError:
        print('未安装 pywin32，尝试使用其他方法...')
        print('请运行：pip install pywin32')
        return False
    except Exception as e:
        print(f'转换失败：{e}')
        return False


if __name__ == '__main__':
    word_file = 'LangGraph 全流程面试拷打文档.docx'
    pdf_file = 'LangGraph 全流程面试拷打文档.pdf'
    
    if Path(word_file).exists():
        convert_word_to_pdf(word_file, pdf_file)
    else:
        print(f'错误：找不到文件 {word_file}')
