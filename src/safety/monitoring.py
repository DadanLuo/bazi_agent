# src/safety/monitoring.py
"""
安全监控告警系统
实时监控安全事件并触发告警
"""
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"           # 信息
    WARNING = "warning"     # 警告
    CRITICAL = "critical"   # 严重
    EMERGENCY = "emergency" # 紧急


class SafetyEventType(Enum):
    """安全事件类型"""
    SUICIDE_ATTEMPT = "suicide_attempt"         # 自杀倾向
    ILLEGAL_REQUEST = "illegal_request"         # 违法请求
    GAMBLING_REQUEST = "gambling_request"       # 赌博请求
    CONTENT_BLOCKED = "content_blocked"         # 内容阻断
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior" # 可疑行为
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded" # 频率超限
    HIGH_RISK_USER = "high_risk_user"           # 高风险用户
    SYSTEM_ANOMALY = "system_anomaly"           # 系统异常


@dataclass
class SafetyEvent:
    """安全事件"""
    event_type: SafetyEventType
    user_id: str
    content: str
    level: AlertLevel
    details: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: f"event_{uuid.uuid4().hex[:8]}")
    
    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "content": self.content,
            "level": self.level.value,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class AlertRule:
    """告警规则"""
    
    def __init__(
        self,
        name: str,
        condition: Callable[[List[SafetyEvent]], bool],
        level: AlertLevel,
        message: str,
        cooldown_minutes: int = 60,
    ):
        self.name = name
        self.condition = condition
        self.level = level
        self.message = message
        self.cooldown_minutes = cooldown_minutes
        self.last_triggered: Optional[datetime] = None
        self.trigger_count = 0
    
    def should_trigger(self, events: List[SafetyEvent]) -> bool:
        """检查是否应该触发告警"""
        if self.last_triggered:
            if datetime.now() - self.last_triggered < timedelta(minutes=self.cooldown_minutes):
                return False
        return self.condition(events)
    
    def mark_triggered(self):
        """标记为已触发"""
        self.last_triggered = datetime.now()
        self.trigger_count += 1


class AlertHandler:
    """告警处理器基类"""
    
    def __init__(self, name: str):
        self.name = name
    
    async def handle(self, alert_data: Dict) -> bool:
        """处理告警"""
        raise NotImplementedError


class EmailAlertHandler(AlertHandler):
    """邮件告警处理器"""
    
    def __init__(self, smtp_config: Dict = None):
        super().__init__("email")
        self.smtp_config = smtp_config or {}
        self._enabled = bool(smtp_config.get("enabled", False))
    
    async def handle(self, alert_data: Dict) -> bool:
        if not self._enabled:
            logger.info(f"📧 邮件告警已禁用: {alert_data['message']}")
            return True
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # 构建邮件
            msg = MIMEMultipart()
            msg["From"] = self.smtp_config.get("from_addr", "noreply@example.com")
            msg["To"] = self.smtp_config.get("to_addrs", "admin@example.com")
            msg["Subject"] = f"[安全告警] {alert_data['message']}"
            
            body = json.dumps(alert_data, ensure_ascii=False, indent=2)
            msg.attach(MIMEText(body, "plain", "utf-8"))
            
            # 发送邮件
            server = smtplib.SMTP(
                self.smtp_config.get("host", "localhost"),
                self.smtp_config.get("port", 25),
            )
            server.login(
                self.smtp_config.get("username", ""),
                self.smtp_config.get("password", ""),
            )
            server.sendmail(
                msg["From"],
                msg["To"].split(","),
                msg.as_string(),
            )
            server.quit()
            
            logger.info(f"📧 邮件告警发送成功: {alert_data['message']}")
            return True
            
        except Exception as e:
            logger.error(f"📧 邮件告警发送失败: {e}")
            return False


class WebhookAlertHandler(AlertHandler):
    """Webhook告警处理器"""
    
    def __init__(self, webhook_url: str, secret: str = None):
        super().__init__("webhook")
        self.webhook_url = webhook_url
        self.secret = secret
    
    async def handle(self, alert_data: Dict) -> bool:
        try:
            import aiohttp
            
            payload = {
                "message": alert_data["message"],
                "level": alert_data["level"],
                "rule_name": alert_data.get("rule_name", "unknown"),
                "timestamp": datetime.now().isoformat(),
                "details": alert_data.get("recent_events", []),
            }
            
            if self.secret:
                import hmac
                import hashlib
                payload["signature"] = hmac.new(
                    self.secret.encode(),
                    json.dumps(payload, sort_keys=True).encode(),
                    hashlib.sha256
                ).hexdigest()
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10,
                ) as response:
                    if response.status == 200:
                        logger.info(f"🔗 Webhook告警发送成功: {alert_data['message']}")
                        return True
                    else:
                        logger.error(f"🔗 Webhook告警发送失败: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"🔗 Webhook告警发送异常: {e}")
            return False


class LogAlertHandler(AlertHandler):
    """日志告警处理器"""
    
    def __init__(self, log_file: str = "data/logs/safety_alerts.log"):
        super().__init__("log")
        self.log_file = log_file
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    async def handle(self, alert_data: Dict) -> bool:
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert_data, ensure_ascii=False) + "\n")
            logger.warning(f"📝 日志告警记录: {alert_data['message']}")
            return True
        except Exception as e:
            logger.error(f"📝 日志告警记录失败: {e}")
            return False


class SafetyMonitor:
    """安全监控器"""
    
    def __init__(self):
        self.events: List[SafetyEvent] = []
        self.user_events: Dict[str, List[SafetyEvent]] = defaultdict(list)
        self.alert_rules: List[AlertRule] = []
        self.alert_handlers: List[AlertHandler] = []
        
        self._init_default_rules()
        self._init_default_handlers()
    
    def _init_default_rules(self):
        """初始化默认告警规则"""
        
        # 规则1：单次自杀倾向立即告警
        self.add_rule(AlertRule(
            name="suicide_immediate",
            condition=lambda events: any(
                e.event_type == SafetyEventType.SUICIDE_ATTEMPT 
                for e in events[-10:]
            ),
            level=AlertLevel.EMERGENCY,
            message="检测到用户自杀倾向，请立即处理！",
            cooldown_minutes=30,
        ))
        
        # 规则2：同一用户短时间内多次被阻断
        self.add_rule(AlertRule(
            name="multiple_blocks",
            condition=lambda events: len([
                e for e in events[-20:]
                if e.event_type == SafetyEventType.CONTENT_BLOCKED
            ]) >= 3,
            level=AlertLevel.WARNING,
            message="用户多次触发内容阻断，可能存在恶意行为",
            cooldown_minutes=60,
        ))
        
        # 规则3：系统整体阻断率异常
        self.add_rule(AlertRule(
            name="high_block_rate",
            condition=lambda events: (
                len(events) >= 100 and
                len([e for e in events[-100:] if e.event_type == SafetyEventType.CONTENT_BLOCKED]) >= 20
            ),
            level=AlertLevel.CRITICAL,
            message="系统阻断率异常升高，可能遭受攻击",
            cooldown_minutes=30,
        ))
        
        # 规则4：违法请求立即告警
        self.add_rule(AlertRule(
            name="illegal_immediate",
            condition=lambda events: any(
                e.event_type == SafetyEventType.ILLEGAL_REQUEST 
                for e in events[-5:]
            ),
            level=AlertLevel.CRITICAL,
            message="检测到违法请求，请立即处理！",
            cooldown_minutes=60,
        ))
        
        # 规则5：赌博请求立即告警
        self.add_rule(AlertRule(
            name="gambling_immediate",
            condition=lambda events: any(
                e.event_type == SafetyEventType.GAMBLING_REQUEST 
                for e in events[-5:]
            ),
            level=AlertLevel.WARNING,
            message="检测到赌博请求，请注意",
            cooldown_minutes=60,
        ))
    
    def _init_default_handlers(self):
        """初始化默认告警处理器"""
        # 日志处理器（始终启用）
        self.add_handler(LogAlertHandler())
        
        # Webhook处理器（需要配置）
        webhook_url = os.getenv("SAFETY_WEBHOOK_URL")
        if webhook_url:
            self.add_handler(WebhookAlertHandler(webhook_url))
        
        # 邮件处理器（需要配置）
        smtp_enabled = os.getenv("SAFETY_EMAIL_ENABLED", "false").lower() == "true"
        if smtp_enabled:
            smtp_config = {
                "enabled": True,
                "host": os.getenv("SMTP_HOST", "localhost"),
                "port": int(os.getenv("SMTP_PORT", 25)),
                "from_addr": os.getenv("SMTP_FROM", "noreply@example.com"),
                "to_addrs": os.getenv("SMTP_TO", "admin@example.com"),
                "username": os.getenv("SMTP_USERNAME", ""),
                "password": os.getenv("SMTP_PASSWORD", ""),
            }
            self.add_handler(EmailAlertHandler(smtp_config))
    
    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.alert_rules.append(rule)
    
    def add_handler(self, handler: AlertHandler):
        """添加告警处理器"""
        self.alert_handlers.append(handler)
    
    async def record_event(self, event: SafetyEvent):
        """记录安全事件"""
        self.events.append(event)
        self.user_events[event.user_id].append(event)
        
        # 保持事件列表在合理大小
        if len(self.events) > 10000:
            self.events = self.events[-5000:]
        
        # 检查告警规则
        await self._check_alerts()
    
    async def _check_alerts(self):
        """检查告警规则"""
        for rule in self.alert_rules:
            if rule.should_trigger(self.events):
                await self._trigger_alert(rule)
    
    async def _trigger_alert(self, rule: AlertRule):
        """触发告警"""
        alert_data = {
            "rule_name": rule.name,
            "level": rule.level.value,
            "message": rule.message,
            "timestamp": datetime.now().isoformat(),
            "trigger_count": rule.trigger_count + 1,
            "recent_events": [
                {
                    "event_id": e.event_id,
                    "type": e.event_type.value,
                    "user_id": e.user_id,
                    "content": e.content[:100],  # 截断内容
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in self.events[-10:]
            ],
        }
        
        logger.warning(f"🚨 安全告警: {rule.name} - {rule.message}")
        
        # 调用所有处理器
        for handler in self.alert_handlers:
            try:
                await handler.handle(alert_data)
            except Exception as e:
                logger.error(f"告警处理器执行失败: {e}")
        
        rule.mark_triggered()
    
    def get_user_risk_score(self, user_id: str) -> float:
        """计算用户风险分数 (0-1)"""
        events = self.user_events.get(user_id, [])
        if not events:
            return 0.0
        
        recent_events = [
            e for e in events
            if datetime.now() - e.timestamp < timedelta(hours=24)
        ]
        
        if not recent_events:
            return 0.0
        
        # 根据事件类型和频率计算风险分数
        score = 0.0
        for event in recent_events:
            if event.event_type == SafetyEventType.SUICIDE_ATTEMPT:
                score += 0.5
            elif event.event_type == SafetyEventType.ILLEGAL_REQUEST:
                score += 0.4
            elif event.event_type == SafetyEventType.GAMBLING_REQUEST:
                score += 0.3
            elif event.event_type == SafetyEventType.CONTENT_BLOCKED:
                score += 0.1
        
        return min(1.0, score)
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            "total_events": len(self.events),
            "events_24h": len([
                e for e in self.events
                if datetime.now() - e.timestamp < timedelta(hours=24)
            ]),
            "user_count": len(self.user_events),
            "user_with_events": len([
                uid for uid, events in self.user_events.items()
                if len(events) > 0
            ]),
            "event_types": {
                et.value: len([
                    e for e in self.events
                    if e.event_type == et
                ])
                for et in SafetyEventType
            },
        }


# 全局监控实例
safety_monitor = SafetyMonitor()
