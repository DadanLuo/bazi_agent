import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


def view_report(report_path: str = 'knowledge_base/processed/deduplication_report.json'):
    """查看查重报告"""

    report_file = Path(report_path)
    if not report_file.exists():
        print(f"❌ 报告文件不存在：{report_file}")
        return

    with open(report_file, 'r', encoding='utf-8') as f:
        report = json.load(f)

    print("\n" + "=" * 60)
    print("📊 八字知识库查重报告")
    print("=" * 60)
    print(f"生成时间：{report['generated_at']}")
    print(f"相似度阈值：{report['similarity_threshold']}")
    print()

    print("📄 文档统计:")
    doc_stats = report['document_stats']
    print(f"   总文档数：{doc_stats['total']}")
    print(f"   重复文档：{doc_stats['duplicates']}")
    print(f"   重复率：{doc_stats['duplicate_rate']}")
    print()

    print("📦 文本块统计:")
    chunk_stats = report['chunk_stats']
    print(f"   总文本块：{chunk_stats['total']}")
    print(f"   重复文本块：{chunk_stats['duplicates']}")
    print(f"   重复率：{chunk_stats['duplicate_rate']}")
    print(f"   移除字符数：{chunk_stats['removed_chars']:,}")
    print()

    print("💾 存储效率:")
    efficiency = report['efficiency_gain']
    print(f"   节省字符：{efficiency['storage_saved_chars']:,}")
    print(f"   节省空间：{efficiency['storage_saved_mb']} MB")
    print()
    print("=" * 60)


if __name__ == '__main__':
    view_report()