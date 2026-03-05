# src/skills/export_skill.py
"""微调数据导出技能 - 支持 OpenAI 和 Alpaca 格式"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import csv

from src.storage import FileStorage, SessionData, Message, MessageRole


class ExportSkill:
    """微调数据导出技能类"""
    
    def __init__(self, storage: Optional[FileStorage] = None):
        """初始化导出技能"""
        self.storage = storage or FileStorage()
    
    def export_openai_format(
        self,
        conversation_id: str,
        output_path: str = "data/finetuning/openai"
    ) -> Optional[str]:
        """导出为 OpenAI 格式"""
        try:
            session_data = self.storage.load_session(conversation_id)
            if not session_data:
                return None
            
            # 获取 OpenAI 格式消息
            messages = session_data.get_openai_format()
            
            # 创建输出目录
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            output_file = output_dir / f"{conversation_id}.jsonl"
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                entry = {"messages": messages}
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            return str(output_file)
            
        except Exception as e:
            print(f"Error exporting OpenAI format: {e}")
            return None
    
    def export_alpaca_format(
        self,
        conversation_id: str,
        output_path: str = "data/finetuning/alpaca"
    ) -> Optional[str]:
        """导出为 Alpaca 格式"""
        try:
            session_data = self.storage.load_session(conversation_id)
            if not session_data:
                return None
            
            # 获取 Alpaca 格式
            alpaca_data = session_data.get_alpaca_format()
            
            # 创建输出目录
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            output_file = output_dir / f"{conversation_id}.jsonl"
            
            # 写入文件
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json.dumps(alpaca_data, ensure_ascii=False) + '\n')
            
            return str(output_file)
            
        except Exception as e:
            print(f"Error exporting Alpaca format: {e}")
            return None
    
    def export_all_openai(
        self,
        output_path: str = "data/finetuning/openai/all.jsonl"
    ) -> Optional[str]:
        """导出所有会话为 OpenAI 格式（合并文件）"""
        try:
            # 创建输出目录
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取所有会话
            sessions = self.storage.list_sessions()
            
            # 写入文件
            with open(output_path, 'w', encoding='utf-8') as f:
                for session_info in sessions:
                    conversation_id = session_info['conversation_id']
                    session_data = self.storage.load_session(conversation_id)
                    
                    if session_data:
                        messages = session_data.get_openai_format()
                        entry = {"messages": messages}
                        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            
            return output_path
            
        except Exception as e:
            print(f"Error exporting all OpenAI format: {e}")
            return None
    
    def export_all_alpaca(
        self,
        output_path: str = "data/finetuning/alpaca/all.jsonl"
    ) -> Optional[str]:
        """导出所有会话为 Alpaca 格式（合并文件）"""
        try:
            # 创建输出目录
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取所有会话
            sessions = self.storage.list_sessions()
            
            # 写入文件
            with open(output_path, 'w', encoding='utf-8') as f:
                for session_info in sessions:
                    conversation_id = session_info['conversation_id']
                    session_data = self.storage.load_session(conversation_id)
                    
                    if session_data:
                        alpaca_data = session_data.get_alpaca_format()
                        f.write(json.dumps(alpaca_data, ensure_ascii=False) + '\n')
            
            return output_path
            
        except Exception as e:
            print(f"Error exporting all Alpaca format: {e}")
            return None
    
    def export_csv(
        self,
        conversation_id: str,
        output_path: str = "data/finetuning/csv"
    ) -> Optional[str]:
        """导出为 CSV 格式"""
        try:
            session_data = self.storage.load_session(conversation_id)
            if not session_data:
                return None
            
            # 创建输出目录
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            output_file = output_dir / f"{conversation_id}.csv"
            
            # 写入 CSV
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['role', 'content'])
                
                for msg in session_data.messages:
                    writer.writerow([msg.role.value, msg.content])
            
            return str(output_file)
            
        except Exception as e:
            print(f"Error exporting CSV: {e}")
            return None
    
    def export_for_training(
        self,
        conversation_id: str,
        format_type: str = "openai",
        output_path: Optional[str] = None
    ) -> Optional[str]:
        """导出用于训练的数据"""
        if format_type == "alpaca":
            return self.export_alpaca_format(conversation_id, output_path)
        else:
            return self.export_openai_format(conversation_id, output_path)
    
    def get_export_stats(self) -> Dict[str, Any]:
        """获取导出统计信息"""
        sessions = self.storage.list_sessions()
        
        total_messages = 0
        total_tokens = 0
        
        for session_info in sessions:
            session_data = self.storage.load_session(session_info['conversation_id'])
            if session_data:
                total_messages += session_info['message_count']
                total_tokens += session_info.get('token_count', 0)
        
        return {
            "total_sessions": len(sessions),
            "total_messages": total_messages,
            "total_tokens": total_tokens,
            "estimated_cost": total_tokens * 0.000001  # 粗略估算
        }
    
    def export_with_filter(
        self,
        filter_fn: callable,
        format_type: str = "openai",
        output_path: str = "data/finetuning/filtered"
    ) -> Optional[str]:
        """带过滤条件的导出"""
        try:
            # 创建输出目录
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取所有会话
            sessions = self.storage.list_sessions()
            
            # 过滤会话
            filtered_sessions = [s for s in sessions if filter_fn(s)]
            
            # 导出过滤后的会话
            for session_info in filtered_sessions:
                conversation_id = session_info['conversation_id']
                self.export_for_training(
                    conversation_id,
                    format_type=format_type,
                    output_path=str(output_dir)
                )
            
            return str(output_dir)
            
        except Exception as e:
            print(f"Error exporting with filter: {e}")
            return None