"""
规则加载器
负责从 src/core/engine/rules/ 目录加载各类命理规则 JSON 文件
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class RuleLoader:
    """
    规则加载器（单例模式）

    解析 JSON 文件列表：
    - tiangan_wuxing.json
    - dizhi_wuxing.json
    - canggan.json
    - geju_rules.json
    - yongshen_rules.json
    - tiaohou_rules.json
    - shier_changsheng.json
    - shensha_rules.json
    - wuxing_relationships.json
    - liunian_rules.json
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 规则文件位于 src/core/engine/rules/ 目录下
        self.config_dir = Path(__file__).parent
        self._cache = {}
        self._load_all_rules()
        self._initialized = True
        logger.info("✅ RuleLoader 初始化完成，已加载所有规则文件")

    def _load_json(self, filename: str) -> Dict:
        """加载 JSON 文件"""
        filepath = self.config_dir / filename
        if not filepath.exists():
            logger.warning(f"⚠️ 规则文件不存在: {filepath}")
            return {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.debug(f"加载规则: {filename}")
                return data
        except Exception as e:
            logger.error(f"❌ 加载规则失败 {filename}: {e}")
            return {}

    def _load_all_rules(self):
        """加载所有规则文件"""
        self._cache["tiangan_wuxing"] = self._load_json("tiangan_wuxing.json")
        self._cache["dizhi_wuxing"] = self._load_json("dizhi_wuxing.json")
        self._cache["canggan"] = self._load_json("canggan.json")
        self._cache["geju_rules"] = self._load_json("geju_rules.json")
        self._cache["yongshen_rules"] = self._load_json("yongshen_rules.json")
        self._cache["tiaohou_rules"] = self._load_json("tiaohou_rules.json")
        self._cache["shier_changsheng"] = self._load_json("shier_changsheng.json")
        self._cache["shensha_rules"] = self._load_json("shensha_rules.json")
        self._cache["wuxing_relations"] = self._load_json("wuxing_relationships.json")
        self._cache["liunian_rules"] = self._load_json("liunian_rules.json")

        # 预处理常用的映射字典，提高访问速度
        self._build_lookup_maps()

    def _build_lookup_maps(self):
        """构建快速查找映射"""
        # 1. 天干五行映射
        self._tiangan_wuxing_map = {}
        for item in self._cache.get("tiangan_wuxing", {}).get("tiangan", []):
            self._tiangan_wuxing_map[item["name"]] = item["wuxing"]

        # 2. 地支五行映射
        self._dizhi_wuxing_map = {}
        for item in self._cache.get("dizhi_wuxing", {}).get("dizhi", []):
            self._dizhi_wuxing_map[item["name"]] = item["wuxing"]

        # 3. 地支藏干映射
        self._canggan_map = {}
        for item in self._cache.get("canggan", {}).get("canggan", []):
            self._canggan_map[item["dizhi"]] = item["cangans"]

        # 4. 十二长生映射
        self._changsheng_map = {}
        for item in self._cache.get("shier_changsheng", {}).get("changsheng", []):
            self._changsheng_map[item["tiangan"]] = item["states"]

        # 5. 天干十神映射
        self._tiangan_shishen_map = self._cache.get("yongshen_rules", {}) \
            .get("tiangan_shishen_map", {}) \
            .get("rules", {})

    # ============== 天干地支相关 ==============

    def get_tiangan_wuxing(self) -> Dict[str, str]:
        """获取天干对应的五行映射 {'甲': '木', ...}"""
        return self._tiangan_wuxing_map

    def get_dizhi_wuxing(self) -> Dict[str, str]:
        """获取地支对应的五行映射 {'子': '水', ...}"""
        return self._dizhi_wuxing_map

    def get_tiangan_info(self, tiangan: str) -> Dict:
        """获取天干详细信息"""
        for item in self._cache.get("tiangan_wuxing", {}).get("tiangan", []):
            if item["name"] == tiangan:
                return item
        return {}

    def get_dizhi_info(self, dizhi: str) -> Dict:
        """获取地支详细信息"""
        for item in self._cache.get("dizhi_wuxing", {}).get("dizhi", []):
            if item["name"] == dizhi:
                return item
        return {}

    # ============== 藏干相关 ==============

    def get_canggan(self, dizhi: str) -> List[Dict[str, Any]]:
        """
        获取地支的藏干列表

        Args:
            dizhi: 地支名称，如 "寅"

        Returns:
            藏干列表，如 [{"tiangan": "甲", "weight": 60, "type": "本气"}, ...]
        """
        return self._canggan_map.get(dizhi, [])

    def get_canggan_tiangan(self, dizhi: str) -> List[str]:
        """获取地支藏干的天干列表"""
        cangan_list = self.get_canggan(dizhi)
        return [item["tiangan"] for item in cangan_list]

    def get_benqi(self, dizhi: str) -> Optional[Dict]:
        """获取地支的本气"""
        cangan_list = self.get_canggan(dizhi)
        for item in cangan_list:
            if item.get("type") == "本气":
                return item
        return None

    # ============== 十神与格局相关 ==============

    def get_shishen_map(self) -> Dict[str, Dict[str, str]]:
        """
        获取天干十神映射
        格式: {'甲': {'甲': '比肩', '乙': '劫财', ...}, ...}
        """
        return self._tiangan_shishen_map

    def get_geju_rules(self) -> Dict:
        """获取格局判断规则 (原始 JSON 结构)"""
        return self._cache.get("geju_rules", {})

    def get_zhengge_rules(self) -> List[Dict]:
        """获取正格规则列表"""
        return self._cache.get("geju_rules", {}).get("zhengge", {}).get("rules", [])

    def get_congge_rules(self) -> List[Dict]:
        """获取从格规则列表"""
        return self._cache.get("geju_rules", {}).get("congge", {}).get("rules", [])

    def get_zage_rules(self) -> List[Dict]:
        """获取杂格规则列表"""
        return self._cache.get("geju_rules", {}).get("zage", {}).get("rules", [])

    # ============== 喜用神与调候相关 ==============

    def get_yongshen_rules(self) -> Dict:
        """获取喜用神规则"""
        return self._cache.get("yongshen_rules", {})

    def get_tiaohou_by_riqian_month(self, ri_qian: str, month_dizhi: str) -> Optional[Dict]:
        """
        根据日干和月支获取调候用神

        Args:
            ri_qian: 日干，如 "甲"
            month_dizhi: 月支，如 "寅"

        Returns:
            调候规则，如 {"yongshen": ["丙", "癸"], "description": "..."}
        """
        tiaohou_list = self._cache.get("tiaohou_rules", {}).get("tiaohou", [])
        for item in tiaohou_list:
            if item.get("riqian") == ri_qian and item.get("month") == month_dizhi:
                return item
        return None

    # ============== 十二长生相关 ==============

    def get_changsheng_state(self, tiangan: str, dizhi: str) -> str:
        """
        获取天干在某地支的十二长生状态

        Args:
            tiangan: 天干
            dizhi: 地支

        Returns:
            状态名称，如 "长生", "帝旺"
        """
        states = self._changsheng_map.get(tiangan, {})
        return states.get(dizhi, "未知")

    def get_changsheng_map(self) -> Dict:
        """获取完整的十二长生映射"""
        return self._changsheng_map

    # ============== 神煞相关 ==============

    def get_shensha_rules(self) -> Dict:
        """获取神煞规则 (原始 JSON 结构)"""
        return self._cache.get("shensha_rules", {})

    def get_jishen_rules(self) -> List[Dict]:
        """获取吉神规则列表"""
        return self._cache.get("shensha_rules", {}).get("jishen", {}).get("rules", [])

    def get_xiongsha_rules(self) -> List[Dict]:
        """获取凶煞规则列表"""
        return self._cache.get("shensha_rules", {}).get("xiongsha", {}).get("rules", [])

    # ============== 五行关系相关 ==============

    def get_wuxing_relations(self) -> Dict:
        """获取五行生克关系规则"""
        return self._cache.get("wuxing_relations", {})

    def get_liuchong(self) -> List[Dict]:
        """获取六冲规则"""
        return self._cache.get("wuxing_relations", {}).get("chong", {}).get("rules", [])

    def get_liuhe(self) -> List[Dict]:
        """获取六合规则"""
        return self._cache.get("wuxing_relations", {}).get("he", {}).get("rules", [])

    # ============== 流年相关 ==============

    def get_liunian_rules(self) -> Dict:
        """获取流年规则"""
        return self._cache.get("liunian_rules", {})

    # ============== 工具方法 ==============

    def reload(self):
        """重新加载所有规则"""
        self._cache.clear()
        self._load_all_rules()
        self._build_lookup_maps()
        logger.info("🔄 规则已重新加载")

    def list_rules(self) -> List[str]:
        """列出所有已加载的规则文件 Key"""
        return list(self._cache.keys())


# 全局单例实例
rule_loader = RuleLoader()


# ============== 便捷接口函数 ==============

def get_tiangan_wuxing() -> Dict[str, str]:
    """获取天干五行映射"""
    return rule_loader.get_tiangan_wuxing()


def get_dizhi_wuxing() -> Dict[str, str]:
    """获取地支五行映射"""
    return rule_loader.get_dizhi_wuxing()


def get_canggan(dizhi: str) -> List[Dict]:
    """获取地支藏干"""
    return rule_loader.get_canggan(dizhi)


def get_geju_rules() -> Dict:
    """获取格局规则"""
    return rule_loader.get_geju_rules()


def get_tiaohou_by_riqian_month(ri_qian: str, month_dizhi: str) -> Optional[Dict]:
    """获取调候用神"""
    return rule_loader.get_tiaohou_by_riqian_month(ri_qian, month_dizhi)


def get_rule(rule_name: str) -> Dict:
    """获取指定规则 (兼容旧接口)"""
    return rule_loader._cache.get(rule_name, {})


# ============== 测试代码 ==============

if __name__ == "__main__":
    print("=" * 60)
    print("🔍 规则加载器测试 (基于实际 JSON 结构)")
    print("=" * 60)

    # 测试天干五行
    print("\n【天干五行映射】")
    print(get_tiangan_wuxing())

    # 测试藏干
    print("\n【寅月藏干】")
    print(get_canggan("寅"))

    # 测试调候
    print("\n【甲木寅月调候】")
    print(get_tiaohou_by_riqian_month("甲", "寅"))

    # 测试十神映射
    print("\n【甲木十神映射】")
    shishen_map = rule_loader.get_shishen_map()
    print(shishen_map.get("甲"))

    # 测试十二长生
    print("\n【甲木在亥的状态】")
    print(rule_loader.get_changsheng_state("甲", "亥"))  # 应为长生

    print("\n✅ 测试完成")
