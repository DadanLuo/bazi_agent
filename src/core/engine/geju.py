"""
格局判断引擎
基于《子平真诠》《渊海子平》规则
"""
import logging
from typing import Dict, List, Optional, Tuple
from src.core.models.bazi_models import FourPillars, Pillar, Tiangan, Dizhi
from .rules import rule_loader
from .wuxing_calculator import WuxingCalculator

logger = logging.getLogger(__name__)


class GejuEngine:
    """
    格局判断引擎

    判断顺序：
    1. 先看是否为从格（特殊情况下）
    2. 再看是否为杂格（魁罡、金神等）
    3. 最后看正格（八正格）
    """

    # 十神映射（日干为基准）
    SHISHEN_MAP = {
        '甲': {'甲': '比肩', '乙': '劫财', '丙': '食神', '丁': '伤官',
               '戊': '偏财', '己': '正财', '庚': '七杀', '辛': '正官',
               '壬': '偏印', '癸': '正印'},
        '乙': {'甲': '劫财', '乙': '比肩', '丙': '伤官', '丁': '食神',
               '戊': '正财', '己': '偏财', '庚': '正官', '辛': '七杀',
               '壬': '正印', '癸': '偏印'},
        '丙': {'甲': '偏印', '乙': '正印', '丙': '比肩', '丁': '劫财',
               '戊': '食神', '己': '伤官', '庚': '偏财', '辛': '正财',
               '壬': '七杀', '癸': '正官'},
        '丁': {'甲': '正印', '乙': '偏印', '丙': '劫财', '丁': '比肩',
               '戊': '伤官', '己': '食神', '庚': '正财', '辛': '偏财',
               '壬': '正官', '癸': '七杀'},
        '戊': {'甲': '七杀', '乙': '正官', '丙': '偏印', '丁': '正印',
               '戊': '比肩', '己': '劫财', '庚': '食神', '辛': '伤官',
               '壬': '偏财', '癸': '正财'},
        '己': {'甲': '正官', '乙': '七杀', '丙': '正印', '丁': '偏印',
               '戊': '劫财', '己': '比肩', '庚': '伤官', '辛': '食神',
               '壬': '正财', '癸': '偏财'},
        '庚': {'甲': '偏财', '乙': '正财', '丙': '七杀', '丁': '正官',
               '戊': '偏印', '己': '正印', '庚': '比肩', '辛': '劫财',
               '壬': '食神', '癸': '伤官'},
        '辛': {'甲': '正财', '乙': '偏财', '丙': '正官', '丁': '七杀',
               '戊': '正印', '己': '偏印', '庚': '劫财', '辛': '比肩',
               '壬': '伤官', '癸': '食神'},
        '壬': {'甲': '食神', '乙': '伤官', '丙': '偏财', '丁': '正财',
               '戊': '七杀', '己': '正官', '庚': '偏印', '辛': '正印',
               '壬': '比肩', '癸': '劫财'},
        '癸': {'甲': '伤官', '乙': '食神', '丙': '正财', '丁': '偏财',
               '戊': '正官', '己': '七杀', '庚': '正印', '辛': '偏印',
               '壬': '劫财', '癸': '比肩'}
    }

    # 月支与格局对应（简化版）
    MONTH_GEJU_MAP = {
        '子': ['正印', '偏印'],
        '丑': ['正官', '七杀', '偏印'],
        '寅': ['正官', '七杀', '偏财'],
        '卯': ['正官', '七杀'],
        '辰': ['正官', '偏财', '正印'],
        '巳': ['正官', '七杀', '正印'],
        '午': ['正官', '七杀', '正印'],
        '未': ['正官', '七杀', '偏印'],
        '申': ['七杀', '偏印', '食神'],
        '酉': ['正官', '七杀'],
        '戌': ['正官', '七杀', '偏印'],
        '亥': ['正印', '偏印', '食神']
    }

    def __init__(self):
        self.rule_loader = rule_loader
        self.wuxing_calc = WuxingCalculator()
        self.tiangan_wuxing = self.rule_loader.get_tiangan_wuxing()

    def get_shishen(self, ri_qian: str, tiangan: str) -> str:
        """获取十神"""
        return self.SHISHEN_MAP.get(ri_qian, {}).get(tiangan, '未知')

    def determine_geju(self, pillars: FourPillars, day_master_strength: Dict) -> Dict:
        """
        判断格局

        Args:
            pillars: 四柱
            day_master_strength: 日主强弱分析结果

        Returns:
            格局判断结果
        """
        ri_qian = pillars.day.tiangan.value
        month_dizhi = pillars.month.dizhi.value

        logger.info(f"格局判断：日干={ri_qian}, 月支={month_dizhi}")

        # 1. 先检查从格
        congge_result = self._check_congge(pillars, day_master_strength)
        if congge_result['is_cong']:
            logger.info(f"判定为从格：{congge_result['geju_type']}")
            return congge_result

        # 2. 检查杂格
        zage_result = self._check_zage(pillars)
        if zage_result['is_zage']:
            logger.info(f"判定为杂格：{zage_result['geju_type']}")
            return zage_result

        # 3. 判断正格
        zhengge_result = self._check_zhengge(pillars, ri_qian, month_dizhi)
        logger.info(f"判定为正格：{zhengge_result['geju_type']}")
        return zhengge_result

    def _check_congge(self, pillars: FourPillars, day_master_strength: Dict) -> Dict:
        """检查是否为从格"""
        strength = day_master_strength.get('strength', 'medium')
        strength_score = day_master_strength.get('score', 50)

        # 从强格：日主极旺
        if strength == 'very_strong' or strength_score >= 80:
            return {
                'is_cong': True,
                'geju_type': '从强格',
                'description': '日主强旺至极，宜顺其势',
                'strength': '特殊'
            }

        # 从弱格：日主极弱
        if strength == 'very_weak' or strength_score <= 20:
            # 进一步判断从什么
            wuxing_score = self.wuxing_calc.calculate_total_score(pillars)
            total = wuxing_score.total()
            if total == 0:
                return {'is_cong': False, 'geju_type': '未知'}

            # 财星最旺→从财
            cai_score = wuxing_score.mu * 0 + wuxing_score.huo * 0 + wuxing_score.tu * 0 + wuxing_score.jin * 0 + wuxing_score.shui * 0
            # 简化判断，实际需根据日干计算财星分数

            return {
                'is_cong': True,
                'geju_type': '从弱格',
                'description': '日主衰弱至极，宜从其弱',
                'strength': '特殊'
            }

        return {'is_cong': False, 'geju_type': '未知'}

    def _check_zage(self, pillars: FourPillars) -> Dict:
        """检查是否为杂格"""
        ri_zhu = f"{pillars.day.tiangan.value}{pillars.day.dizhi.value}"
        shi_zhu = f"{pillars.hour.tiangan.value}{pillars.hour.dizhi.value}"

        geju_rules = self.rule_loader.get_geju_rules()
        zage_rules = geju_rules.get('zage', {}).get('rules', [])

        for rule in zage_rules:
            if rule['name'] == '魁罡格':
                if ri_zhu in rule.get('rizhu', []):
                    return {
                        'is_zage': True,
                        'geju_type': '魁罡格',
                        'description': rule.get('description', ''),
                        'strength': '特殊'
                    }
            elif rule['name'] == '日德格':
                if ri_zhu in rule.get('rizhu', []):
                    return {
                        'is_zage': True,
                        'geju_type': '日德格',
                        'description': rule.get('description', ''),
                        'strength': '中上'
                    }
            elif rule['name'] == '日贵格':
                if ri_zhu in rule.get('rizhu', []):
                    return {
                        'is_zage': True,
                        'geju_type': '日贵格',
                        'description': rule.get('description', ''),
                        'strength': '中上'
                    }

        return {'is_zage': False, 'geju_type': '未知'}

    def _check_zhengge(self, pillars: FourPillars, ri_qian: str, month_dizhi: str) -> Dict:
        """判断正格（八正格）"""
        # 获取月令藏干
        month_canggan = self.rule_loader.get_canggan(month_dizhi)

        # 获取天干十神
        month_tg = pillars.month.tiangan.value
        month_tg_shishen = self.get_shishen(ri_qian, month_tg)

        # 月令本气十神
        benqi_shishen = None
        for cangan in month_canggan:
            if cangan['type'] == '本气':
                benqi_shishen = self.get_shishen(ri_qian, cangan['tiangan'])
                break

        # 判断格局
        geju_type = '正格'
        geju_description = ''
        strength = '中等'

        # 根据月令本气和透干判断
        if benqi_shishen == '正官':
            geju_type = '正官格'
            geju_description = '月令正官，为人正直，有管理才能'
            strength = '中上'
        elif benqi_shishen == '七杀':
            geju_type = '七杀格'
            geju_description = '月令七杀，性格刚强，有决断力'
            strength = '中上'
        elif benqi_shishen == '正印':
            geju_type = '正印格'
            geju_description = '月令正印，为人仁慈，有学识'
            strength = '中上'
        elif benqi_shishen == '偏印':
            geju_type = '偏印格'
            geju_description = '月令偏印，思维独特，有专长'
            strength = '中等'
        elif benqi_shishen == '正财':
            geju_type = '正财格'
            geju_description = '月令正财，勤俭持家，重实际'
            strength = '中等'
        elif benqi_shishen == '偏财':
            geju_type = '偏财格'
            geju_description = '月令偏财，善于理财，有商业头脑'
            strength = '中等'
        elif benqi_shishen == '食神':
            geju_type = '食神格'
            geju_description = '月令食神，为人温和，有才华'
            strength = '中上'
        elif benqi_shishen == '伤官':
            geju_type = '伤官格'
            geju_description = '月令伤官，聪明伶俐，有创造力'
            strength = '中等'
        else:
            geju_type = '常格'
            geju_description = '无明显格局，以五行平衡论'
            strength = '中等'

        return {
            'is_zage': False,
            'geju_type': geju_type,
            'description': geju_description,
            'strength': strength,
            'month_shishen': benqi_shishen,
            'month_tg_shishen': month_tg_shishen
        }