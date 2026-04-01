"""
==============================================================================
喜用神推导引擎
==============================================================================

功能说明：
    本模块实现了喜用神的推导逻辑，基于《子平真诠》《穷通宝鉴》等传统
    命理典籍的规则。喜用神是八字分析的核心概念，用于指导命主如何趋吉
    避凶，调整命运走向。

推导逻辑：
    1. 根据日主强弱确定基本喜忌
    2. 根据格局类型调整喜用神
    3. 根据调候需求调整喜用神
    4. 综合得出最终喜用神

==============================================================================
"""

import logging
from typing import Dict, List, Optional
from src.core.models.bazi_models import FourPillars, WuxingScore
from .rules import rule_loader
from .wuxing_calculator import WuxingCalculator
from .geju import GejuEngine

logger = logging.getLogger(__name__)


class YongshenEngine:
    """
    ==============================================================================
    喜用神推导引擎
    ==============================================================================
    
    功能说明：
        喜用神推导引擎，负责根据八字四柱、日主强弱和格局类型推导出命局
        的喜用神和忌神。喜用神是命主应该追求和利用的五行，忌神是应该
        避免和克制的五行。
    
    推导顺序：
        1. 根据日主强弱确定基本喜忌
        2. 根据格局类型调整喜用神
        3. 根据调候需求调整喜用神
        4. 综合得出最终喜用神
    
    核心方法：
        - get_shishen_by_wuxing() - 根据日干和五行获取十神
        - determine_yongshen() - 推导喜用神
        - _get_basic_yongshen() - 获取基本喜用神
        - _adjust_by_geju() - 根据格局调整
        - _get_tiaohou_yongshen() - 获取调候用神
        - _combine_yongshen() - 综合喜用神
        - _get_jishen() - 获取忌神
        - _generate_reason() - 生成推导理由
    
    使用场景：
        - 喜用神推导
        - 命局分析
        - 趋吉避凶建议
    
    ==============================================================================
    """

    # 五行对应十神（需根据日干动态计算）
    # 用于从五行反推十神
    WUXING_SHISHEN = {
        '木': ['比肩', '劫财'],
        '火': ['食神', '伤官'],
        '土': ['正财', '偏财'],
        '金': ['正官', '七杀'],
        '水': ['正印', '偏印']
    }

    def __init__(self):
        """
        初始化喜用神推导引擎，加载规则文件和五行计算器。
        """
        self.rule_loader = rule_loader
        self.wuxing_calc = WuxingCalculator()
        self.tiangan_wuxing = self.rule_loader.get_tiangan_wuxing()

    def get_shishen_by_wuxing(self, ri_qian: str, wuxing: str) -> str:
        """
        ==============================================================================
        根据日干和五行获取十神
        ==============================================================================
        
        功能说明：
            根据日干和五行，反推该五行对应的十神。
        
        参数说明：
            ri_qian (str): 日干（如：甲、乙、丙等）
            wuxing (str): 五行（如：木、火、土等）
        
        返回值：
            str: 十神名称（比肩、劫财、食神、伤官、正财、偏财、
                 正官、七杀、正印、偏印）
        
        ==============================================================================
        """
        # 找到对应此五行的天干
        for tg, wx in self.tiangan_wuxing.items():
            if wx == wuxing:
                # 获取此天干对日干的十神
                shishen_map = GejuEngine.SHISHEN_MAP.get(ri_qian, {})
                return shishen_map.get(tg, '未知')
        return '未知'

    def determine_yongshen(self, pillars: FourPillars,
                           day_master_strength: Dict,
                           geju_result: Dict) -> Dict:
        """
        ==============================================================================
        推导喜用神
        ==============================================================================
        
        功能说明：
            综合日主强弱、格局类型和调候需求，推导出命局的喜用神和忌神。
        
        参数说明：
            pillars (FourPillars): 四柱对象
            day_master_strength (Dict): 日主强弱分析结果
            geju_result (Dict): 格局判断结果
        
        返回值：
            Dict: 喜用神推导结果，包含：
                - yongshen (List[str]): 喜用神五行列表
                - jishen (List[str]): 忌神五行列表
                - tiaohou (List[str]): 调候用神五行列表
                - reason (str): 推导理由
                - description (str): 喜用神描述
        
        推导流程：
            1. 根据日主强弱确定基本喜忌
            2. 根据格局类型调整喜用神
            3. 根据调候需求调整喜用神
            4. 综合判断得出最终喜用神
        
        ==============================================================================
        """
        ri_qian = pillars.day.tiangan.value
        ri_qian_wx = self.tiangan_wuxing.get(ri_qian, '金')
        month_dizhi = pillars.month.dizhi.value

        logger.info(f"喜用神推导：日干={ri_qian}({ri_qian_wx}), 月支={month_dizhi}")

        # 1. 根据日主强弱确定基本喜忌
        strength = day_master_strength.get('strength', 'medium')
        basic_yongshen, basic_jishen = self._get_basic_yongshen(strength, ri_qian)
        logger.info(f"基本喜用：{basic_yongshen}, 基本忌神：{basic_jishen}")

        # 2. 根据格局调整
        geju_type = geju_result.get('geju_type', '常格')
        geju_yongshen = self._adjust_by_geju(geju_type, basic_yongshen)
        logger.info(f"格局调整后：{geju_yongshen}")

        # 3. 根据调候调整
        tiaohou_yongshen = self._get_tiaohou_yongshen(ri_qian, month_dizhi)
        logger.info(f"调候用神：{tiaohou_yongshen}")

        # 4. 综合判断
        final_yongshen = self._combine_yongshen(basic_yongshen, geju_yongshen, tiaohou_yongshen)
        final_jishen = self._get_jishen(final_yongshen, ri_qian_wx)

        logger.info(f"最终喜用：{final_yongshen}, 最终忌神：{final_jishen}")

        return {
            'yongshen': final_yongshen,
            'jishen': final_jishen,
            'tiaohou': tiaohou_yongshen,
            'reason': self._generate_reason(strength, geju_type, tiaohou_yongshen),
            'description': f"喜{','.join(final_yongshen)}, 忌{','.join(final_jishen)}"
        }

    def _get_basic_yongshen(self, strength: str, ri_qian: str) -> tuple:
        """
        ==============================================================================
        根据日主强弱获取基本喜用神
        ==============================================================================
        
        功能说明：
            根据日主强弱确定基本的喜用神和忌神。
        
        参数说明：
            strength (str): 日主强弱等级（strong/medium/weak/very_weak）
            ri_qian (str): 日干
        
        返回值：
            tuple: (yongshen, jishen) 喜用神列表和忌神列表
        
        判断逻辑：
            1. 身强（strong/very_strong）：
               喜克泄耗（财、官、食伤）
               忌生扶（印、比劫）
            2. 身弱（weak/very_weak）：
               喜生扶（印、比劫）
               忌克泄耗（财、官、食伤）
            3. 中和（medium）：
               视情况而定
        
        ==============================================================================
        """
        ri_qian_wx = self.tiangan_wuxing.get(ri_qian, '金')

        if strength in ['strong', 'very_strong']:
            # 身强：喜克泄耗（财、官、食伤）
            yongshen = self._get_ke_xie_hao_wuxing(ri_qian_wx)
            jishen = self._get_sheng_fu_wuxing(ri_qian_wx)
        elif strength in ['weak', 'very_weak']:
            # 身弱：喜生扶（印、比劫）
            yongshen = self._get_sheng_fu_wuxing(ri_qian_wx)
            jishen = self._get_ke_xie_hao_wuxing(ri_qian_wx)
        else:
            # 中和：视情况而定
            yongshen = [ri_qian_wx]  # 暂用日主五行
            jishen = []

        return yongshen, jishen

    def _get_sheng_fu_wuxing(self, ri_wx: str) -> List[str]:
        """
        ==============================================================================
        获取生扶日主的五行（印、比劫）
        ==============================================================================
        
        功能说明：
            获取能够生扶日主的五行，包括印星和比劫。
        
        参数说明：
            ri_wx (str): 日干五行
        
        返回值：
            List[str]: 生扶五行列表（印 + 比劫）
        
        五行关系：
            - 印星：生我者
            - 比劫：同我者
        
        ==============================================================================
        """
        sheng_map = {'木': '水', '火': '木', '土': '火', '金': '土', '水': '金'}
        sheng_wx = sheng_map.get(ri_wx, '土')  # 印
        return [sheng_wx, ri_wx]  # 印 + 比劫

    def _get_ke_xie_hao_wuxing(self, ri_wx: str) -> List[str]:
        """
        ==============================================================================
        获取克泄耗日主的五行（财、官、食伤）
        ==============================================================================
        
        功能说明：
            获取能够克泄耗日主的五行，包括官杀、食伤和财星。
        
        参数说明：
            ri_wx (str): 日干五行
        
        返回值：
            List[str]: 克泄耗五行列表（官 + 食伤）
        
        五行关系：
            - 官杀：克我者
            - 食伤：我生者
            - 财星：我克者
        
        ==============================================================================
        """
        ke_map = {'木': '金', '火': '水', '土': '木', '金': '火', '水': '土'}
        xie_map = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}
        ke_wx = ke_map.get(ri_wx, '火')  # 官
        xie_wx = xie_map.get(ri_wx, '火')  # 食伤
        return [ke_wx, xie_wx]

    def _adjust_by_geju(self, geju_type: str, basic_yongshen: List[str]) -> List[str]:
        """
        ==============================================================================
        根据格局调整喜用神
        ==============================================================================
        
        功能说明：
            根据格局类型对基本喜用神进行调整。
        
        参数说明：
            geju_type (str): 格局类型
            basic_yongshen (List[str]): 基本喜用神列表
        
        返回值：
            List[str]: 调整后的喜用神列表
        
        调整规则：
            1. 从格：顺其势或从其弱，保持基本喜用神
            2. 正官格：喜印护官，添加土行
            3. 七杀格：喜食神制杀或印化杀，添加火行
        
        ==============================================================================
        """
        # 从格特殊处理
        if '从强' in geju_type:
            return basic_yongshen  # 顺其势
        elif '从弱' in geju_type:
            return basic_yongshen  # 从其弱

        # 正官格：喜印护官
        if geju_type == '正官格':
            if '土' not in basic_yongshen:
                basic_yongshen.append('土')

        # 七杀格：喜食神制杀或印化杀
        if geju_type == '七杀格':
            if '火' not in basic_yongshen:
                basic_yongshen.append('火')

        return basic_yongshen

    def _get_tiaohou_yongshen(self, ri_qian: str, month_dizhi: str) -> List[str]:
        """
        ==============================================================================
        获取调候用神
        ==============================================================================
        
        功能说明：
            根据日干和月支获取调候用神。调候用神用于调节命局的寒暖燥湿，
            使命局达到平衡状态。
        
        参数说明：
            ri_qian (str): 日干
            month_dizhi (str): 月支
        
        返回值：
            List[str]: 调候用神五行列表
        
        调候原则：
            - 寒：喜火（调候）
            - 热：喜水（调候）
            - 干：喜水（调候）
            - 湿：喜火（调候）
        
        ==============================================================================
        """
        tiaohou_rule = self.rule_loader.get_tiaohou_by_riqian_month(ri_qian, month_dizhi)
        if tiaohou_rule:
            # 调候用神是天干，需转为五行
            tiangan_list = tiaohou_rule.get('yongshen', [])
            wuxing_list = [self.tiangan_wuxing.get(tg, '土') for tg in tiangan_list]
            return list(set(wuxing_list))
        return []

    def _combine_yongshen(self, basic: List[str], geju: List[str],
                          tiaohou: List[str]) -> List[str]:
        """
        ==============================================================================
        综合三种喜用神
        ==============================================================================
        
        功能说明：
            综合基本喜用神、格局调整后的喜用神和调候用神，得出最终的喜用神。
        
        参数说明：
            basic (List[str]): 基本喜用神列表
            geju (List[str]): 格局调整后的喜用神列表
            tiaohou (List[str]): 调候用神列表
        
        返回值：
            List[str]: 综合后的喜用神列表（最多 3 个）
        
        ==============================================================================
        """
        combined = basic.copy()
        for wx in geju:
            if wx not in combined:
                combined.append(wx)
        for wx in tiaohou:
            if wx not in combined:
                combined.append(wx)

        # 限制最多 3 个
        return combined[:3]

    def _get_jishen(self, yongshen: List[str], ri_wx: str) -> List[str]:
        """
        ==============================================================================
        根据喜用神推导忌神
        ==============================================================================
        
        功能说明：
            根据喜用神推导出忌神。忌神是与喜用神相对的五行。
        
        参数说明：
            yongshen (List[str]): 喜用神列表
            ri_wx (str): 日干五行
        
        返回值：
            List[str]: 忌神列表（最多 2 个）
        
        ==============================================================================
        """
        all_wuxing = ['木', '火', '土', '金', '水']
        jishen = [wx for wx in all_wuxing if wx not in yongshen]
        return jishen[:2]  # 最多 2 个忌神

    def _generate_reason(self, strength: str, geju_type: str,
                         tiaohou: List[str]) -> str:
        """
        ==============================================================================
        生成推导理由
        ==============================================================================
        
        功能说明：
            生成喜用神推导的理由说明，用于向用户解释推导过程。
        
        参数说明：
            strength (str): 日主强弱等级
            geju_type (str): 格局类型
            tiaohou (List[str]): 调候用神列表
        
        返回值：
            str: 推导理由说明
        
        ==============================================================================
        """
        reasons = []

        if strength in ['weak', 'very_weak']:
            reasons.append(f"日主偏弱，宜生扶")
        elif strength in ['strong', 'very_strong']:
            reasons.append(f"日主偏强，宜克泄")
        else:
            reasons.append(f"日主中和，视格局而定")

        if geju_type != '常格':
            reasons.append(f"格局为{geju_type}")

        if tiaohou:
            reasons.append(f"调候需{','.join(tiaohou)}")

        return "；".join(reasons)
