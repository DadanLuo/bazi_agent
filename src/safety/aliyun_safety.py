# src/safety/aliyun_safety.py
"""
==============================================================================
阿里云内容安全API集成
==============================================================================

功能说明：
    本模块集成了阿里云内容安全API，作为本地规则引擎的第二道防线。
    提供更全面的内容审核能力，包括反垃圾、政治、暴恐、 abuse 等场景。

安全机制：
    1. 本地规则引擎：快速、低成本的敏感词匹配
    2. 阿里云API：更全面的内容审核，包括图片、文本等
    3. 降级机制：API 不可用时自动降级到本地规则

审核场景：
    - antispam: 反垃圾
    - politics: 政治敏感
    - terrorism: 暴恐
    - abuse: 虐待

==============================================================================
"""

import logging
import hashlib
import hmac
import base64
import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class AliyunSafetyResult(Enum):
    """
    ==============================================================================
    阿里云内容安全审核结果
    ==============================================================================
    
    结果说明：
        - PASS: 通过
        - REVIEW: 需要人工审核
        - BLOCK: 阻断
    
    ==============================================================================
    """
    PASS = "pass"       # 通过
    REVIEW = "review"   # 需要人工审核
    BLOCK = "block"     # 阻断


@dataclass
class AliyunSafetyResponse:
    """
    ==============================================================================
    阿里云内容安全API响应
    ==============================================================================
    
    属性说明：
        - code: 响应码
        - msg: 响应消息
        - result: 审核结果
        - suggestions: 建议列表
        - details: 详细信息
    
    ==============================================================================
    """
    code: int
    msg: str
    result: Optional[AliyunSafetyResult]
    suggestions: List[str]
    details: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AliyunSafetyResponse":
        """
        ==============================================================================
        从API响应创建对象
        ==============================================================================
        
        功能说明：
            从阿里云API返回的字典数据创建 AliyunSafetyResponse 对象。
        
        参数说明：
            data (Dict[str, Any]): API 响应数据
        
        返回值：
            AliyunSafetyResponse: 响应对象
        
        ==============================================================================
        """
        result = None
        if "suggestion" in data:
            if data["suggestion"] == "pass":
                result = AliyunSafetyResult.PASS
            elif data["suggestion"] == "review":
                result = AliyunSafetyResult.REVIEW
            elif data["suggestion"] == "block":
                result = AliyunSafetyResult.BLOCK
        
        suggestions = []
        details = {}
        
        if "results" in data and data["results"]:
            for r in data["results"]:
                if "suggestion" in r:
                    suggestions.append(r["suggestion"])
                details.update(r)
        
        return cls(
            code=data.get("code", 0),
            msg=data.get("msg", ""),
            result=result,
            suggestions=suggestions,
            details=details,
        )
    
    def is_blocked(self) -> bool:
        """
        ==============================================================================
        是否需要阻断
        ==============================================================================
        
        返回值：
            bool: 是否需要阻断
        
        ==============================================================================
        """
        return self.result == AliyunSafetyResult.BLOCK
    
    def needs_review(self) -> bool:
        """
        ==============================================================================
        是否需要人工审核
        ==============================================================================
        
        返回值：
            bool: 是否需要人工审核
        
        ==============================================================================
        """
        return self.result == AliyunSafetyResult.REVIEW


class AliyunTextSafetyClient:
    """
    ==============================================================================
    阿里云内容安全API文本审核客户端
    ==============================================================================
    
    功能说明：
        阿里云内容安全API文本审核客户端，支持单个和批量文本审核。
        使用 HMAC-SHA1 签名进行身份认证。
    
    核心方法：
        - scan_text(): 审核单个文本
        - scan_texts(): 批量审核文本
    
    使用场景：
        - 用户输入审核
        - LLM 输出审核
        - 批量内容审核
    
    ==============================================================================
    """
    
    def __init__(
        self,
        access_key_id: str = None,
        access_key_secret: str = None,
        endpoint: str = "green-cip.cn-shanghai.aliyuncs.com",
    ):
        """
        ==============================================================================
        初始化客户端
        ==============================================================================
        
        功能说明：
            初始化阿里云内容安全API客户端。
        
        参数说明：
            access_key_id (str): 阿里云 AccessKey ID
            access_key_secret (str): 阿里云 AccessKey Secret
            endpoint (str): API 端点，默认为上海区域
        
        环境变量：
            - DASHSCOPE_API_KEY: 用作 AccessKey ID（备选）
            - ALIYUN_ACCESS_KEY_SECRET: AccessKey Secret
        
        ==============================================================================
        """
        self.access_key_id = access_key_id or self._get_env("DASHSCOPE_API_KEY")
        self.access_key_secret = access_key_secret or self._get_env("ALIYUN_ACCESS_KEY_SECRET")
        self.endpoint = endpoint
        
        # 检查是否配置了必要的凭据
        if not self.access_key_id or not self.access_key_secret:
            logger.warning(
                "⚠️ 阿里云内容安全API凭据未配置，将跳过远程审核。"
                "请设置 ALIYUN_ACCESS_KEY_ID 和 ALIYUN_ACCESS_KEY_SECRET 环境变量"
            )
            self._enabled = False
        else:
            self._enabled = True
    
    def _get_env(self, key: str) -> Optional[str]:
        """
        ==============================================================================
        从环境变量获取值
        ==============================================================================
        
        参数说明：
            key (str): 环境变量名称
        
        返回值：
            Optional[str]: 环境变量值，如果不存在则返回 None
        
        ==============================================================================
        """
        import os
        return os.getenv(key)
    
    def _generate_auth_headers(
        self,
        method: str,
        path: str,
        body: str,
        timestamp: str,
    ) -> Dict[str, str]:
        """
        ==============================================================================
        生成认证头
        ==============================================================================
        
        功能说明：
            生成阿里云内容安全API所需的认证头。
            使用 HMAC-SHA1 签名进行身份认证。
        
        参数说明：
            method (str): HTTP 方法（GET/POST）
            path (str): 请求路径
            body (str): 请求体
            timestamp (str): 时间戳（ISO 8601 格式）
        
        返回值：
            Dict[str, str]: 认证头字典
        
        签名算法：
            1. 构建待签名字符串：METHOD\nPATH\nBODY\n
            2. 使用 HMAC-SHA1 计算签名
            3. Base64 编码签名
        
        ==============================================================================
        """
        # 构建待签名字符串
        string_to_sign = f"{method}\n{path}\n{body}\n"
        
        # 使用HMAC-SHA1计算签名
        signature = hmac.new(
            self.access_key_secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1
        ).digest()
        
        # Base64编码
        signature_base64 = base64.b64encode(signature).decode("utf-8")
        
        return {
            "Authorization": f"acs {self.access_key_id}:{signature_base64}",
            "Content-Type": "application/json",
            "Date": timestamp,
        }
    
    def _build_request_body(
        self,
        texts: List[str],
        scenes: List[str] = None,
    ) -> Dict[str, Any]:
        """
        ==============================================================================
        构建API请求体
        ==============================================================================
        
        功能说明：
            构建阿里云内容安全API的请求体。
        
        参数说明：
            texts (List[str]): 待审核的文本列表
            scenes (List[str]): 审核场景，默认为 ["antispam", "politics", "terrorism", "abuse"]
        
        返回值：
            Dict[str, Any]: 请求体字典
        
        请求体格式：
            {
                "scenes": ["antispam", "politics", "terrorism", "abuse"],
                "tasks": [
                    {
                        "dataId": "task_0_1234567890",
                        "content": "待审核文本"
                    },
                    ...
                ]
            }
        
        ==============================================================================
        """
        if scenes is None:
            scenes = ["antispam", "politics", "terrorism", "abuse"]
        
        return {
            "scenes": scenes,
            "tasks": [
                {
                    "dataId": f"task_{i}_{int(time.time() * 1000)}",
                    "content": text,
                }
                for i, text in enumerate(texts)
            ],
        }
    
    def scan_text(
        self,
        text: str,
        scenes: List[str] = None,
    ) -> AliyunSafetyResponse:
        """
        ==============================================================================
        审核单个文本
        ==============================================================================
        
        功能说明：
            调用阿里云内容安全API审核单个文本。
        
        参数说明：
            text (str): 待审核文本
            scenes (List[str]): 审核场景列表
        
        返回值：
            AliyunSafetyResponse: 审核结果
        
        异常处理：
            - API 调用失败：返回错误响应
            - 网络异常：返回错误响应
        
        ==============================================================================
        """
        if not self._enabled:
            return AliyunSafetyResponse(
                code=200,
                msg="阿里云内容安全API未启用",
                result=None,
                suggestions=[],
                details={},
            )
        
        try:
            import requests
            
            # 构建请求
            url = f"https://{self.endpoint}/green/text/scan"
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            
            request_body = self._build_request_body([text], scenes)
            body_str = json.dumps(request_body, ensure_ascii=False)
            
            # 构建请求头
            headers = self._generate_auth_headers(
                method="POST",
                path="/green/text/scan",
                body=body_str,
                timestamp=timestamp,
            )
            
            # 发送请求
            response = requests.post(
                url,
                headers=headers,
                data=body_str.encode("utf-8"),
                timeout=10,
            )
            
            # 解析响应
            if response.status_code == 200:
                data = response.json()
                return AliyunSafetyResponse.from_dict(data)
            else:
                logger.error(
                    f"阿里云内容安全API请求失败: "
                    f"status={response.status_code}, body={response.text}"
                )
                return AliyunSafetyResponse(
                    code=response.status_code,
                    msg=f"API请求失败: {response.status_code}",
                    result=None,
                    suggestions=[],
                    details={},
                )
                
        except Exception as e:
            logger.error(f"阿里云内容安全API调用异常: {e}")
            return AliyunSafetyResponse(
                code=500,
                msg=f"调用异常: {str(e)}",
                result=None,
                suggestions=[],
                details={},
            )
    
    def scan_texts(
        self,
        texts: List[str],
        scenes: List[str] = None,
    ) -> List[AliyunSafetyResponse]:
        """
        ==============================================================================
        批量审核文本
        ==============================================================================
        
        功能说明：
            调用阿里云内容安全API批量审核多个文本。
        
        参数说明：
            texts (List[str]): 待审核文本列表
            scenes (List[str]): 审核场景列表
        
        返回值：
            List[AliyunSafetyResponse]: 审核结果列表
        
        ==============================================================================
        """
        if not self._enabled:
            return [
                AliyunSafetyResponse(
                    code=200,
                    msg="阿里云内容安全API未启用",
                    result=None,
                    suggestions=[],
                    details={},
                )
                for _ in texts
            ]
        
        try:
            import requests
            
            url = f"https://{self.endpoint}/green/text/scan"
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            
            request_body = self._build_request_body(texts, scenes)
            body_str = json.dumps(request_body, ensure_ascii=False)
            
            headers = self._generate_auth_headers(
                method="POST",
                path="/green/text/scan",
                body=body_str,
                timestamp=timestamp,
            )
            
            response = requests.post(
                url,
                headers=headers,
                data=body_str.encode("utf-8"),
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                if "data" in data and "results" in data["data"]:
                    for r in data["data"]["results"]:
                        results.append(AliyunSafetyResponse.from_dict(r))
                else:
                    results = [
                        AliyunSafetyResponse(
                            code=data.get("code", 0),
                            msg=data.get("msg", ""),
                            result=None,
                            suggestions=[],
                            details={},
                        )
                    ]
                
                return results
            else:
                logger.error(
                    f"批量审核失败: status={response.status_code}, body={response.text}"
                )
                return [
                    AliyunSafetyResponse(
                        code=response.status_code,
                        msg=f"API请求失败: {response.status_code}",
                        result=None,
                        suggestions=[],
                        details={},
                    )
                ] * len(texts)
                
        except Exception as e:
            logger.error(f"批量审核异常: {e}")
            return [
                AliyunSafetyResponse(
                    code=500,
                    msg=f"调用异常: {str(e)}",
                    result=None,
                    suggestions=[],
                    details={},
                )
            ] * len(texts)


class AliyunSafetyChecker:
    """
    ==============================================================================
    阿里云内容安全集成检查器
    ==============================================================================
    
    功能说明：
        阿里云内容安全集成检查器，作为本地规则引擎的补充。
        优先使用阿里云API，降级到本地规则。
    
    核心方法：
        - check_text(): 检查单个文本
        - batch_check(): 批量检查文本
    
    检查策略：
        1. 优先使用阿里云API
        2. 如果阿里云API不可用，降级到本地规则
        3. 如果本地规则也检查出问题，阻断内容
    
    使用场景：
        - 用户输入审核
        - LLM 输出审核
        - 批量内容审核
    
    ==============================================================================
    """
    
    def __init__(self):
        """
        ==============================================================================
        初始化阿里云安全检查器
        ==============================================================================
        
        功能说明：
            初始化阿里云安全检查器，创建 API 客户端实例。
        
        ==============================================================================
        """
        self.client = AliyunTextSafetyClient()
        self._enabled = self.client._enabled
    
    def check_text(
        self,
        text: str,
        use_local_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        ==============================================================================
        检查文本安全性
        ==============================================================================
        
        功能说明：
            检查文本的安全性，优先使用阿里云API，降级到本地规则。
        
        参数说明：
            text (str): 待检查文本
            use_local_fallback (bool): 是否使用本地规则作为兜底，默认为 True
        
        返回值：
            Dict[str, Any]: 检查结果，包含：
                - blocked (bool): 是否被阻断
                - needs_review (bool): 是否需要人工审核
                - suggestion (str): 建议（pass/review/block）
                - aliyun_result (AliyunSafetyResponse): 阿里云审核结果
                - local_result (SafetyResult): 本地审核结果
                - message (str): 检查消息
        
        检查流程：
            1. 优先使用阿里云API
            2. 如果阿里云API不可用，降级到本地规则
            3. 如果本地规则检查出问题，阻断内容
        
        ==============================================================================
        """
        result = {
            "blocked": False,
            "needs_review": False,
            "suggestion": "pass",
            "aliyun_result": None,
            "local_result": None,
            "message": "",
        }
        
        # 1. 优先使用阿里云API
        if self._enabled:
            try:
                response = self.client.scan_text(text)
                result["aliyun_result"] = response
                
                if response.is_blocked():
                    result["blocked"] = True
                    result["suggestion"] = "block"
                    result["message"] = response.msg or "内容包含违规信息"
                elif response.needs_review():
                    result["needs_review"] = True
                    result["suggestion"] = "review"
                    result["message"] = "内容需要人工审核"
                else:
                    # 通过阿里云审核，但可能仍有本地规则需要检查
                    if use_local_fallback:
                        from src.safety.safety import SafetyChecker
                        local_checker = SafetyChecker()
                        local_result = local_checker.check_input(text)
                        result["local_result"] = local_result
                        
                        if local_result.blocked:
                            result["blocked"] = True
                            result["suggestion"] = "block"
                            result["message"] = local_result.message
            except Exception as e:
                logger.error(f"阿里云审核异常: {e}")
                # 降级到本地规则
                if use_local_fallback:
                    from src.safety.safety import SafetyChecker
                    local_checker = SafetyChecker()
                    local_result = local_checker.check_input(text)
                    result["local_result"] = local_result
                    
                    if local_result.blocked:
                        result["blocked"] = True
                        result["message"] = local_result.message
        else:
            # 未启用阿里云API，使用本地规则
            if use_local_fallback:
                from src.safety.safety import SafetyChecker
                local_checker = SafetyChecker()
                local_result = local_checker.check_input(text)
                result["local_result"] = local_result
                
                if local_result.blocked:
                    result["blocked"] = True
                    result["message"] = local_result.message
        
        return result
    
    def batch_check(
        self,
        texts: List[str],
    ) -> List[Dict[str, Any]]:
        """
        ==============================================================================
        批量检查文本
        ==============================================================================
        
        功能说明：
            批量检查多个文本的安全性。
        
        参数说明：
            texts (List[str]): 待检查文本列表
        
        返回值：
            List[Dict[str, Any]]: 检查结果列表
        
        ==============================================================================
        """
        results = []
        
        if self._enabled:
            try:
                responses = self.client.scan_texts(texts)
                
                for i, response in enumerate(responses):
                    result = {
                        "blocked": response.is_blocked(),
                        "needs_review": response.needs_review(),
                        "suggestion": response.result.value if response.result else "unknown",
                        "aliyun_result": response,
                        "message": response.msg if response.msg else "",
                    }
                    results.append(result)
            except Exception as e:
                logger.error(f"批量审核异常: {e}")
                # 降级到本地规则
                from src.safety.safety import SafetyChecker
                local_checker = SafetyChecker()
                
                for text in texts:
                    local_result = local_checker.check_input(text)
                    results.append({
                        "blocked": local_result.blocked,
                        "needs_review": False,
                        "suggestion": "block" if local_result.blocked else "pass",
                        "local_result": local_result,
                        "message": local_result.message,
                    })
        else:
            # 未启用阿里云API，使用本地规则
            from src.safety.safety import SafetyChecker
            local_checker = SafetyChecker()
            
            for text in texts:
                local_result = local_checker.check_input(text)
                results.append({
                    "blocked": local_result.blocked,
                    "needs_review": False,
                    "suggestion": "block" if local_result.blocked else "pass",
                    "local_result": local_result,
                    "message": local_result.message,
                })
        
        return results
