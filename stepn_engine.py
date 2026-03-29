"""
STEPN OG Economy Simulation Engine v2
=======================================
全3レルム（Solana / BNB Chain / Polygon）対応の経済シミュレータ。
GSTキャップ、GMTプール（クラシック/虹）、虹靴エンハンス、半減期対応。

データソース:
- STEPN Whitepaper: https://whitepaper.stepn.com/
- CoinGecko GST/GMT: https://www.coingecko.com/en/coins/green-satoshi-token
- Dune Analytics: https://dune.com/nguyentoan/STEPN-(GMT,-GST)-Core-Metrics
- STEPN-MARKET.GUIDE: https://stepn-market.guide/
- TradingView: GMT Halving 2026-01-01
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ============================================================
# データ定数（出典付き）
# ============================================================

# --- エナジーシステム (出典: whitepaper.stepn.com/running-module/energy-system) ---
ENERGY_TABLE = {1: 2, 3: 4, 9: 9, 15: 12, 30: 20}

RARITY_ENERGY_BONUS = {
    "Common": 0, "Uncommon": 1, "Rare": 2, "Epic": 3, "Legendary": 4
}

# --- GSTキャップ (出典: whitepaper.stepn.com/earning-module/gst-cap-mechanics) ---
GST_DAILY_CAP_BASE = 300       # 基本上限 300 GST/日
GST_DAILY_CAP_MAX = 2300       # GMT Burnで最大 2300 GST/日
# GMTバーンによるキャップ解放コスト（段階推定）
# 出典: whitepaper + コミュニティ集約。Lv30スニーカーで 600 cap → 12,600 GMT
GST_CAP_UNLOCK_COST_GMT = {
    300: 0, 600: 12_600, 900: 30_000, 1200: 55_000,
    1500: 90_000, 1800: 140_000, 2100: 210_000, 2300: 280_000,
}

# --- GMTアーニングプール ---
# 出典: STEPN Whitepaper GMT Earning, TradingView halving report
# GMT Earning開始: 2022-09-28
# 初回半減期: 2026-01-01 (プール50%削減)
# 総プール: 6B × 30% = 1.8B GMT (ユーザー配分)
# 半減前日次排出量推定: ~1.0M GMT/日 (Dune Analytics集約)
GMT_EARNING_POOL_TOTAL = 1_800_000_000   # 1.8B GMT
GMT_EARNING_START_DATE = "2022-09-28"
GMT_HALVING_INTERVAL_DAYS = 1190         # ≈3年3ヶ月 (初回2026-01-01)
# 2026-01-01半減後の推定日次排出量
GMT_DAILY_EMISSION_POST_HALVING = 500_000  # 0.5M GMT/日 (半減後)

# プール比率 (出典: p2e.game STEPN GMT Earning Plans)
GMT_POOL_CLASSIC_RATIO = 0.40    # クラシックプール 40%
GMT_POOL_RAINBOW_RATIO = 0.60    # レインボープール 60%
# クラシック: Lv30+通常靴、Comfort属性依存
# レインボー: 虹靴専用、Rainbow Power属性依存

# --- 虹靴 (Rainbow Sneakers) ---
# 出典: whitepaper.stepn.com/game-module/enhancement-system
# 出典: playtoearn.com STEPN Rainbow Sneakers report
ENHANCE_INPUT_SHOES = 5          # エンハンスに5足必要
ENHANCE_RAINBOW_PROB_COMMON = 0.005     # Common 5足→虹靴: 0.5%
ENHANCE_RAINBOW_PROB_UNCOMMON = 0.025   # Uncommon 5足→虹靴: 2.5% (5倍)
ENHANCE_RAINBOW_PROB_RARE = 0.0         # Rare以上は虹靴排出なし
# エンハンスコスト (GST+GMT、レアリティ別)
# 出典: whitepaper.stepn.com/game-module/enhancement-system
# 5足同レアリティ → 1足上位レアリティ (+ 虹靴チャンス)
# コストはDynamic Enhancement Cost (DEC) でGST/GMT比に依存するが、
# 現在のGST≈0.002USD低価格環境ではほぼ固定。以下はアプリ内実測値(2025-2026)
ENHANCE_COST = {
    "Common":   {"GST": 360, "GMT": 40},    # 5 Common → 1 Uncommon (+ 虹0.5%)
    "Uncommon": {"GST": 1080, "GMT": 120},   # 5 Uncommon → 1 Rare (+ 虹2.5%)
    "Rare":     {"GST": 2160, "GMT": 240},   # 5 Rare → 1 Epic
    "Epic":     {"GST": 4320, "GMT": 480},   # 5 Epic → 1 Legendary
}

# --- ミントコスト (レアリティ別、ミント回数0の親2足合計) ---
# 出典: ipaddressguide.org, stepn.vanxh.dev mint calculator
# 2022/04変更後: Common=50%GST/50%GMT、Uncommon以上はGMT比率増
# ミント回数が増えるとコスト増(0-mint基準の1.0〜3.0倍)。平均ミント回数1.5を想定
MINT_COST = {
    "Common":    {"GST": 120, "GMT": 80},    # C×C 0-mint: 120+80, 平均≈180+120
    "Uncommon":  {"GST": 480, "GMT": 320},   # U×U 0-mint: 480+320
    "Rare":      {"GST": 1440, "GMT": 960},  # R×R 0-mint: 1440+960
    "Epic":      {"GST": 4320, "GMT": 2880}, # E×E 推定 (3倍スケール)
    "Legendary": {"GST": 12960, "GMT": 8640},# L×L 推定
}
# ミント回数加算係数（0-mint基準。回数1→1.2倍, 2→1.5倍, ...平均1.5mintで約1.3倍）
MINT_COUNT_MULTIPLIER_AVG = 1.3
# 虹靴スペック
RAINBOW_MIN_ENERGY = 6           # 最低6エナジー消費必要
RAINBOW_FLOOR_GMT = 88_888       # フロアプライス (stepn-market.guide, 2026-03)
RAINBOW_HP_RECOVERABLE = False   # HP回復不可、0でGMT獲得停止→実質退役
RAINBOW_HP_LIFESPAN_DAYS = 75    # 実測: 2〜3ヶ月でHP枯渇 → 中央値約75日

# --- レベルアップコスト (出典: wealthquint.com, stepn.guide) ---
LEVEL_UP_COST = {}
_gst_costs = [1,2,3,4,10,20,30,40,50,60,70,80,90,100,110,120,130,140,150,160,
              170,180,190,200,210,220,230,240,250,260]
_gmt_costs = [0,0,0,0,0,0,0,0,0,0,10,0,0,0,0,0,0,0,0,0,30,0,0,0,0,0,0,0,0,29]
for i in range(30):
    LEVEL_UP_COST[i] = (_gst_costs[i], _gmt_costs[i])

TOTAL_LEVELUP_GST = sum(v[0] for v in LEVEL_UP_COST.values())
TOTAL_LEVELUP_GMT = sum(v[1] for v in LEVEL_UP_COST.values())

# --- ジェム経済 ---
# 出典: whitepaper.stepn.com/game-fi-elements/gems-and-sockets
# 出典: whitepaper.stepn.com/game-module/gem-upgrade
# 出典: ktrainUSA Twitter, コミュニティ集約
GEM_TYPES = ["Efficiency", "Luck", "Comfort", "Resilience"]
GEM_TYPE_COLORS = {"Efficiency": "Yellow", "Luck": "Blue", "Comfort": "Red", "Resilience": "Purple"}

# ジェムレベル別属性ボーナス (出典: whitepaper + コミュニティ検証)
GEM_ATTRIBUTE_BONUS = {
    1: 2, 2: 8, 3: 25, 4: 72, 5: 200,
    6: 580, 7: 1650, 8: 2800, 9: 6789,
}
# 覚醒効果 (ベース属性に対する%ボーナス)
GEM_AWAKENING_PERCENT = {
    1: 20, 2: 70, 3: 220, 4: 600, 5: 1600,
    6: 4400, 7: 12800, 8: 22000, 9: 66000,
}

# ジェムアップグレードコスト (3個同レベル同タイプ → 1個上位)
# 出典: ktrainUSA (@ktrainUSA_STEPN), whitepaper, アプリ内確認
GEM_UPGRADE_COST = {
    # level: (GST, GMT)
    1: (50, 0),      # Lv1→2: 50 GST
    2: (100, 0),     # Lv2→3: 100 GST
    3: (200, 0),     # Lv3→4: 200 GST
    4: (400, 100),   # Lv4→5: 400 GST + 100 GMT
    5: (800, 200),   # Lv5→6: 800 GST + 200 GMT
    6: (1600, 400),  # Lv6→7: 1600 GST + 400 GMT
    7: (3200, 800),  # Lv7→8: 3200 GST + 800 GMT
    8: (6400, 1600), # Lv8→9: 6400 GST + 1600 GMT
}

# ジェムアップグレード成功率 (出典: whitepaper)
GEM_UPGRADE_SUCCESS_RATE = {
    1: 0.35, 2: 0.55, 3: 0.65, 4: 0.75, 5: 0.85,
    6: 1.00, 7: 1.00, 8: 1.00,
}

# ソケット解放 (スニーカーLv5,10,15,20で各1ソケット, 最大4)
SOCKET_UNLOCK_LEVELS = [5, 10, 15, 20]
SOCKET_UNLOCK_COST_GST = 20  # 1ソケットあたり

# ジェムレベル別推定分布 (全ジェム中の割合, 2026-03推定)
# 高レベルほど極めて少ない (成功率×3個消費の累乗)
GEM_LEVEL_DISTRIBUTION = {
    1: 0.55, 2: 0.25, 3: 0.12, 4: 0.05, 5: 0.02,
    6: 0.008, 7: 0.001, 8: 0.0005, 9: 0.0005,
}
# タイプ別分布 (おおむね均等だがEfficiency人気)
GEM_TYPE_DISTRIBUTION = {
    "Efficiency": 0.35, "Luck": 0.20, "Comfort": 0.25, "Resilience": 0.20,
}

# ジェムフロアプライス GMT (出典: stepn-market.guide 推定, 2026-03)
GEM_FLOOR_PRICE_GMT = {
    1: 5, 2: 30, 3: 200, 4: 1500, 5: 12000,
    6: 80000, 7: 500000, 8: 2000000, 9: 10000000,
}

# 1ユーザーあたり平均ジェム保有数 (推定)
AVG_GEMS_PER_USER = 4.0
# 日次ジェムアップグレード試行率 (DAU中)
# 大半のユーザーは毎日アップグレードしない。週1程度の想定
DAILY_GEM_UPGRADE_RATE = 0.003

# --- ミステリーボックス (MB) 経済 ---
# 出典: whitepaper.stepn.com/earning-module/mystery-box-system
# 出典: stepn-market.guide/cheat-sheet, 黒ブタ(blackpigtail.com) MB開封データ
# 出典: パレゾウ(@parezoparezo) MB中身データ, Otty(@OttySTEPNer1) MBチャート
# 出典: kightblog.co.jp/cryptoassets/nft/stepn-mysterybox/
# MBレベル1-10: Luck×Energy で品質決定。開封カウントダウン自動開始。
# 開封ベースコスト (GST) — 待機時間完了後の最低開封費用
MB_OPENING_COST_GST = {
    1: 5, 2: 7, 3: 10, 4: 35, 5: 100,
    6: 255, 7: 523, 8: 1024, 9: 1818, 10: 2699,
}
# 開封までの待機時間 (日) — この時間経過後にベースコストで開封可能
MB_WAIT_DAYS = {
    1: 2, 2: 3, 3: 4, 4: 5, 5: 8,
    6: 10, 7: 12, 8: 14, 9: 16, 10: 18,
}
# MBドロップに必要な最低消費エナジー / 最低Luck目安
# 出典: lollipopkz.xyz/stepn-mystery-box/, STEPNstatsコミュニティデータ
MB_ENERGY_LUCK_REQ = {
    # mb_level: (min_energy, min_luck)
    1: (1, 0),      # 低エナジーでもドロップする
    2: (2, 0),      # 低エナジーでもドロップする
    3: (5, 15),     # 5E+, Luck15+ が目安
    4: (5, 30),     # 5E+, Luck30+ (Lv1ジェム確定, Lv2ジェム35%)
    5: (8, 60),     # 8E+, Luck60+ (Lv2ジェム100%)
    6: (12, 100),   # 12E+, Luck100+
    7: (20, 200),   # 20E+, Luck200+
    8: (20, 400),   # 20E+, Luck400+
    9: (20, 500),   # 20E+, Luck500+ (Lv3ジェム100%)
    10: (20, 800),  # 20E+, 超高Luck (Lv4ジェム出る可能性あり)
}
# MB内ジェムドロップ確率 — MBレベル別に異なる
# 出典: パレゾウ(@parezoparezo) コミュニティ開封データ集約
# Lv5以上はLv2ジェム100%、Lv9以上はLv3ジェム100%
MB_GEM_LEVEL_PROB = {
    # mb_level: {gem_level: probability}
    1: {1: 0.60, 2: 0.00, 3: 0.00, 4: 0.00},  # Lv1ジェムのみ (出ない場合も多い)
    2: {1: 0.80, 2: 0.00, 3: 0.00, 4: 0.00},  # Lv1ジェムのみ
    3: {1: 0.75, 2: 0.25, 3: 0.00, 4: 0.00},  # Lv2ジェム25%
    4: {1: 0.60, 2: 0.35, 3: 0.05, 4: 0.00},  # Lv2ジェム35%
    5: {1: 0.00, 2: 0.85, 3: 0.14, 4: 0.01},  # Lv2ジェム100%, Lv3も出る
    6: {1: 0.00, 2: 0.65, 3: 0.30, 4: 0.05},  # Lv3ジェム割合UP
    7: {1: 0.00, 2: 0.40, 3: 0.50, 4: 0.10},  # Lv3中心
    8: {1: 0.00, 2: 0.20, 3: 0.60, 4: 0.20},  # Lv3-4中心
    9: {1: 0.00, 2: 0.00, 3: 0.70, 4: 0.30},  # Lv3ジェム100%
    10: {1: 0.00, 2: 0.00, 3: 0.50, 4: 0.50}, # Lv4ジェム高確率
}
# MBレベル別: 平均ジェム個数、平均スクロール個数
# 出典: 黒ブタ MB開封データ, コミュニティ報告集約
MB_LOOT_TABLE = {
    # mb_level: (avg_gems, avg_scrolls)
    1: (0.10, 0.10),   # 大半が空。まれにLv1ジェムやCommonスクロール
    2: (0.30, 0.50),   # スクロール中心。ジェムは30%程度
    3: (0.80, 1.00),   # ジェム1個が多い + スクロール1枚
    4: (1.20, 1.20),   # ジェム1-2個 + スクロール1枚
    5: (2.00, 1.50),   # ジェム2個 + スクロール1-2枚
    6: (2.50, 2.00),   # ジェム2-3個 + スクロール2枚
    7: (3.00, 2.50),   # ジェム3個 + スクロール2-3枚
    8: (4.00, 3.00),   # ジェム4個 + スクロール3枚
    9: (5.00, 3.50),   # ジェム5個 + スクロール3-4枚
    10: (6.00, 4.00),  # ジェム6個 + スクロール4枚
}
# MBレベル別スクロールレアリティ (主にドロップされるレアリティ)
# MBのレアリティに対応: Lv1-2=Common, Lv3-4=Uncommon, Lv5-6=Rare, Lv7-8=Epic, Lv9-10=Legendary
MB_SCROLL_RARITY = {
    1: {"Common": 1.0},
    2: {"Common": 0.95, "Uncommon": 0.05},
    3: {"Common": 0.50, "Uncommon": 0.45, "Rare": 0.05},
    4: {"Common": 0.25, "Uncommon": 0.50, "Rare": 0.20, "Epic": 0.05},
    5: {"Common": 0.10, "Uncommon": 0.30, "Rare": 0.40, "Epic": 0.15, "Legendary": 0.05},
    6: {"Common": 0.05, "Uncommon": 0.15, "Rare": 0.45, "Epic": 0.25, "Legendary": 0.10},
    7: {"Common": 0.00, "Uncommon": 0.10, "Rare": 0.30, "Epic": 0.40, "Legendary": 0.20},
    8: {"Common": 0.00, "Uncommon": 0.05, "Rare": 0.20, "Epic": 0.45, "Legendary": 0.30},
    9: {"Common": 0.00, "Uncommon": 0.00, "Rare": 0.10, "Epic": 0.40, "Legendary": 0.50},
    10: {"Common": 0.00, "Uncommon": 0.00, "Rare": 0.05, "Epic": 0.30, "Legendary": 0.65},
}
# ミント1回に2枚スクロール必要 (レアリティ一致)
SCROLLS_PER_MINT = 2

# --- GSTバーン内訳比率（推定） ---
GST_BURN_RATIO = {
    "level_up": 0.25, "gem_upgrade": 0.18, "repair": 0.15,
    "mint": 0.10, "socket": 0.05, "enhance": 0.10, "gst_cap_burn": 0.05,
    "mb_open": 0.07, "other": 0.05,
}

# --- トークン価格 (出典: CoinGecko, 2026-03) ---
GMT_TOTAL_SUPPLY = 6_000_000_000
GMT_CIRCULATING_2026 = 4_270_000_000
GST_PRICE_SOL = 0.00175
GST_PRICE_BSC = 0.00098
GST_PRICE_POL = 0.0015
GMT_PRICE = 0.012

# --- ユーザー数 (出典: Binance Square / Dune Analytics) ---
PEAK_MAU = 705_452
MAU_2023_FEB = 42_965
ESTIMATED_MAU_2026 = 30_000


# ============================================================
# パラメータ定義
# ============================================================

@dataclass
class RealmParams:
    """レルム別パラメータ"""
    name: str = "Solana"
    user_share: float = 0.70
    gst_price: float = GST_PRICE_SOL
    sneaker_floor_gmt: float = 90.0
    avg_sneakers_per_user: float = 3.5
    avg_energy_per_user: float = 5.0
    base_gst_per_energy: float = 5.0
    gmt_earn_per_energy: float = 0.03
    gmt_earner_ratio: float = 0.05


@dataclass
class UserSegment:
    """ユーザーセグメント（エナジーキャパ × 消化率モデル）"""
    label: str
    n_realms: int
    sneakers_per_realm: int
    user_ratio: float
    energy_consumption_rate: float  # 時間制約反映 (0〜1)
    gmt_earner_ratio: float         # Lv30+比率
    daily_mint_ratio: float
    gst_cap_level: float = GST_DAILY_CAP_BASE  # このセグメントのGSTキャップ
    has_rainbow: float = 0.0        # 虹靴保有率 (0〜1)
    mb_drop_rate: float = 0.0       # MBドロップ確率/日 (0〜1)
    avg_mb_level: float = 1.0       # 平均MBレベル (1〜10)

    @property
    def energy_capacity(self) -> float:
        per_realm = ENERGY_TABLE.get(self.sneakers_per_realm, 2)
        return min(per_realm * self.n_realms, 60.0)

    @property
    def energy_consumed(self) -> float:
        return self.energy_capacity * self.energy_consumption_rate

    @property
    def total_sneakers(self) -> int:
        return self.sneakers_per_realm * self.n_realms


DEFAULT_SEGMENTS: List[UserSegment] = [
    # label, n_realms, snk/realm, ratio, cons_rate, gmt_r, mint_r, gst_cap, rainbow,
    #                                                                         mb_drop, avg_mb_lv
    # MBドロップ率・平均MBレベルの根拠 (stepn-market.guide, STEPNstatsデータ):
    # - Lv1-2: 低E/低Luckでもドロップ (2E+でLv1出る)
    # - Lv3: 5E+, Luck15+ | Lv4: 5E+, Luck30+ | Lv5: 8E+, Luck60+
    # - Lv6: 12E+, Luck100+ | Lv7-8: 20E+, Luck200-400+ | Lv9-10: 20E+, Luck500+
    # 現実的には大半のプレイヤーがLv1-4。Lv5+はLuck特化ビルドのみ。
    # --- 1レルム ---
    UserSegment("1R/2E カジュアル",     1, 1,  0.25, 1.00, 0.00, 0.000, 300, 0.000, 0.30, 1.0),
    #   2E: Luck低い。Lv1中心 (空が多い、損益マイナス)
    UserSegment("1R/4E ライト",         1, 3,  0.22, 0.95, 0.01, 0.002, 300, 0.000, 0.50, 1.5),
    #   4E: Luck15+で Lv1-2中心。界王拳で5E可能
    UserSegment("1R/9E ミドル",         1, 9,  0.18, 0.85, 0.03, 0.005, 300, 0.000, 0.75, 2.5),
    #   9E: ほぼ毎日ドロップ。Luck30+でLv3-4狙い
    UserSegment("1R/12E ヘビー",        1, 15, 0.08, 0.75, 0.08, 0.008, 600, 0.001, 0.85, 3.5),
    #   12E: Luck100+でLv4-5。Luck特化ならLv6も
    UserSegment("1R/20E ガチ勢",        1, 30, 0.04, 0.60, 0.15, 0.010, 900, 0.003, 0.90, 5.0),
    #   20E: Luck200+でLv5-6。超Luck振りでLv7も
    # --- 2レルム ---
    UserSegment("2R/8E サブ持ち",       2, 3,  0.06, 0.80, 0.02, 0.003, 300, 0.000, 0.60, 2.0),
    UserSegment("2R/18E 中級マルチ",    2, 9,  0.05, 0.65, 0.05, 0.006, 600, 0.002, 0.80, 3.5),
    UserSegment("2R/24E 上級マルチ",    2, 15, 0.03, 0.50, 0.12, 0.008, 900, 0.006, 0.85, 4.5),
    UserSegment("2R/40E ガチマルチ",    2, 30, 0.02, 0.40, 0.20, 0.010, 1500, 0.013, 0.92, 6.0),
    # --- 3レルム（ホエール） ---
    UserSegment("3R/27E トリプル中",    3, 9,  0.03, 0.50, 0.10, 0.005, 900, 0.006, 0.80, 4.0),
    UserSegment("3R/36E トリプル上",    3, 15, 0.02, 0.45, 0.18, 0.008, 1500, 0.013, 0.90, 5.5),
    UserSegment("3R/60E MAX",           3, 30, 0.02, 0.67, 0.25, 0.012, 2300, 0.025, 0.95, 7.0),
    # MAX60E: 消化率0.67 → 60×0.67 ≈ 40E/日（≈200分）ユーザーフィードバック反映
    # 虹靴保有率0.025 → 600人中15人 ≈ 全体の約30%の虹靴がMAX60E層に集中
    # Luck500+で Lv7-8。トップ層はLv9も出る可能性あるがコスト2699GSTで現実的に開封せず
]


@dataclass
class UserDistribution:
    """ユーザーセグメント分布"""
    segments: List[UserSegment] = field(default_factory=lambda: list(DEFAULT_SEGMENTS))
    rarity_distribution: Dict[str, float] = field(default_factory=lambda: {
        "Common": 0.70, "Uncommon": 0.20, "Rare": 0.07,
        "Epic": 0.025, "Legendary": 0.005,
    })
    type_distribution: Dict[str, float] = field(default_factory=lambda: {
        "Walker": 0.20, "Jogger": 0.45, "Runner": 0.20, "Trainer": 0.15,
    })


@dataclass
class GmtPoolParams:
    """GMTアーニングプール設定"""
    # 日次排出量 (半減後, 2026-01-01〜)
    daily_emission: float = GMT_DAILY_EMISSION_POST_HALVING
    classic_ratio: float = GMT_POOL_CLASSIC_RATIO    # 40%
    rainbow_ratio: float = GMT_POOL_RAINBOW_RATIO    # 60%
    # 次回半減期までの日数（2026-01-01から約3年後）
    next_halving_day: int = 1095  # シミュ開始からの日数
    # 半減係数
    halving_factor: float = 0.5
    # プール残量追跡
    pool_remaining: float = 900_000_000  # 半減後の残量推定 (1.8B × 50%)


@dataclass
class RainbowParams:
    """虹靴経済パラメータ"""
    # エンハンス (5足→1足、一定確率で虹靴)
    enhance_prob_common: float = ENHANCE_RAINBOW_PROB_COMMON
    enhance_prob_uncommon: float = ENHANCE_RAINBOW_PROB_UNCOMMON
    # 日次エンハンス試行率（全DAU中）
    daily_enhance_rate: float = 0.002
    # エンハンスコスト（レアリティ分布加重平均で自動算出）
    # Common70% + Uncommon20% = 加重平均
    # = 0.70*360 + 0.20*1080 + 0.07*2160 + 0.03*4320 ≈ 748 GST
    # = 0.70*40  + 0.20*120  + 0.07*240  + 0.03*480  ≈  83 GMT
    enhance_avg_gst: float = 748.0
    enhance_avg_gmt: float = 83.0
    # 虹靴からのスニーカー消費（5足/回）
    shoes_consumed_per_enhance: int = ENHANCE_INPUT_SHOES
    # 虹靴HP減衰率/日（回復不可、2〜3ヶ月で枯渇）
    rainbow_hp_decay_per_day: float = 0.0133  # 1/75日 ≈ 1.33%/日 → 約75日で退役
    # 虹靴の推定流通量 (2026-03)
    rainbow_supply: float = 50  # stepn-market.guide: 16リスティング → 全体推定50足程度
    # 虹靴のRainbow Power平均
    avg_rainbow_power: float = 100.0


@dataclass
class SimParams:
    """シミュレーション全体パラメータ"""
    n_days: int = 365
    total_users: int = 30_000
    monthly_new_users: int = 500
    monthly_churn_rate: float = 0.05
    daily_active_ratio: float = 0.60

    realms: Dict[str, RealmParams] = field(default_factory=lambda: {
        "Solana": RealmParams(name="Solana", user_share=0.70,
                              gst_price=GST_PRICE_SOL, sneaker_floor_gmt=90.0),
        "BNB": RealmParams(name="BNB", user_share=0.20,
                            gst_price=GST_PRICE_BSC, sneaker_floor_gmt=120.0),
        "Polygon": RealmParams(name="Polygon", user_share=0.10,
                                gst_price=GST_PRICE_POL, sneaker_floor_gmt=200.0),
    })

    user_dist: UserDistribution = field(default_factory=UserDistribution)
    gmt_pool: GmtPoolParams = field(default_factory=GmtPoolParams)
    rainbow: RainbowParams = field(default_factory=RainbowParams)

    gst_initial_supply: float = 1_500_000_000
    gmt_circulating: float = GMT_CIRCULATING_2026
    avg_efficiency_attr: float = 50.0
    efficiency_coefficient: float = 0.1
    # ミントコストはレアリティ分布から自動算出（固定）
    # 加重平均: Common70%×(120*1.3) + Uncommon20%×(480*1.3) + Rare7%×(1440*1.3) + ...
    # GST: 0.70*156 + 0.20*624 + 0.07*1872 + 0.025*5616 + 0.005*16848 ≈ 500 GST
    # GMT: 0.70*104 + 0.20*416 + 0.07*1248 + 0.025*3744 + 0.005*11232 ≈ 339 GMT
    avg_mint_cost_gst: float = 590.0   # レアリティ加重平均 × ミント回数係数1.3
    avg_mint_cost_gmt: float = 393.0
    gst_burn_ratio_map: Dict[str, float] = field(default_factory=lambda: dict(GST_BURN_RATIO))
    gmt_monthly_burn: float = 2_000_000
    gmt_monthly_unlock: float = 15_000_000


# ============================================================
# シミュレーションエンジン
# ============================================================

def calc_weighted_energy(user_dist: UserDistribution) -> float:
    return sum(seg.energy_consumed * seg.user_ratio for seg in user_dist.segments)


def calc_gst_earn_per_energy(base: float, efficiency: float, coeff: float) -> float:
    return base + efficiency * coeff


def simulate(params: SimParams) -> pd.DataFrame:
    """メインシミュレーション v2: GSTキャップ + GMTプール + 虹靴対応"""
    days = params.n_days
    records = []
    segments = params.user_dist.segments

    total_users = float(params.total_users)
    gst_supply = {r: params.gst_initial_supply * rp.user_share
                  for r, rp in params.realms.items()}
    gmt_circulating = params.gmt_circulating
    total_sneakers = total_users * sum(
        seg.total_sneakers * seg.user_ratio for seg in segments
    )

    # スクロール在庫追跡 (レアリティ別)
    scroll_inventory = {r: 0.0 for r in ["Common", "Uncommon", "Rare", "Epic", "Legendary"]}

    # レアリティ別スニーカー追跡
    rarity_names = list(params.user_dist.rarity_distribution.keys())
    sneakers_by_rarity = {
        r: total_sneakers * ratio
        for r, ratio in params.user_dist.rarity_distribution.items()
    }

    # ジェム経済追跡
    total_gems = total_users * AVG_GEMS_PER_USER
    gems_by_level = {lv: total_gems * ratio for lv, ratio in GEM_LEVEL_DISTRIBUTION.items()}

    # GMTプール状態
    gmt_pool_remaining = params.gmt_pool.pool_remaining
    gmt_daily_emission = params.gmt_pool.daily_emission
    rainbow_supply = params.rainbow.rainbow_supply

    gst_per_energy = {
        rname: calc_gst_earn_per_energy(
            rp.base_gst_per_energy, params.avg_efficiency_attr,
            params.efficiency_coefficient,
        )
        for rname, rp in params.realms.items()
    }
    realm_list = list(params.realms.items())

    for day in range(days):
        month = day // 30

        # --- ユーザー数更新 ---
        if day > 0 and day % 30 == 0:
            total_users = max(100, total_users + params.monthly_new_users
                              - total_users * params.monthly_churn_rate)

        # --- GMT半減期チェック ---
        if day == params.gmt_pool.next_halving_day:
            gmt_daily_emission *= params.gmt_pool.halving_factor

        dau = total_users * params.daily_active_ratio

        # --- GMTプール日次分配 ---
        actual_gmt_emission = min(gmt_daily_emission, gmt_pool_remaining)
        gmt_classic_pool = actual_gmt_emission * params.gmt_pool.classic_ratio
        gmt_rainbow_pool = actual_gmt_emission * params.gmt_pool.rainbow_ratio
        gmt_pool_remaining -= actual_gmt_emission

        rec = {"day": day, "month": month, "total_users": total_users, "dau": dau}

        total_gst_minted = 0.0
        total_gst_burned = 0.0
        total_gmt_earned_classic = 0.0
        total_gmt_earned_rainbow = 0.0
        total_gmt_burned_users = 0.0
        daily_sneakers_minted = 0.0
        daily_sneakers_enhanced = 0.0
        daily_rainbow_created = 0.0
        daily_mb_opened = 0.0
        daily_mb_gst_cost = 0.0
        daily_mb_gems_created = 0.0
        daily_mb_scrolls_created = 0.0
        daily_scrolls_used = 0.0
        mb_gems_by_level = {lv: 0.0 for lv in range(1, 5)}  # ジェムLv1-4

        realm_gst_minted_map = {r: 0.0 for r in params.realms}
        realm_gst_burned_map = {r: 0.0 for r in params.realms}
        realm_users_map = {r: 0.0 for r in params.realms}
        burn_multiplier = sum(params.gst_burn_ratio_map.values())

        # --- セグメント別計算 ---
        for seg in segments:
            seg_dau = dau * seg.user_ratio
            if seg_dau < 0.01:
                continue

            energy_used = seg.energy_consumed
            # GSTキャップ適用: 1人あたりGST/日を制限
            uncapped_gst_per_user = energy_used * 10.0  # base + efficiency
            capped_gst_per_user = min(uncapped_gst_per_user, seg.gst_cap_level)

            if seg.n_realms == 1:
                for rname, rp in realm_list:
                    r_users = seg_dau * rp.user_share
                    r_gst = r_users * capped_gst_per_user
                    r_burn = r_gst * burn_multiplier * 0.85
                    r_gmt_burn = (
                        r_users * seg.daily_mint_ratio * params.avg_mint_cost_gmt +
                        r_users * seg.gmt_earner_ratio * 0.1 * 5.0
                    )
                    r_mint = r_users * seg.daily_mint_ratio
                    realm_gst_minted_map[rname] += r_gst
                    realm_gst_burned_map[rname] += r_burn
                    realm_users_map[rname] += r_users
                    total_gst_minted += r_gst
                    total_gst_burned += r_burn
                    total_gmt_burned_users += r_gmt_burn
                    daily_sneakers_minted += r_mint
            else:
                sorted_realms = sorted(realm_list, key=lambda x: -x[1].user_share)
                active_realms = sorted_realms[:seg.n_realms]
                gst_per_realm = capped_gst_per_user / seg.n_realms
                for rname, rp in active_realms:
                    r_users = seg_dau / seg.n_realms
                    r_gst = r_users * gst_per_realm
                    r_burn = r_gst * burn_multiplier * 0.85
                    r_gmt_burn = (
                        r_users * seg.daily_mint_ratio * params.avg_mint_cost_gmt +
                        r_users * seg.gmt_earner_ratio * 0.1 * 5.0
                    )
                    r_mint = r_users * seg.daily_mint_ratio
                    realm_gst_minted_map[rname] += r_gst
                    realm_gst_burned_map[rname] += r_burn
                    realm_users_map[rname] += r_users
                    total_gst_minted += r_gst
                    total_gst_burned += r_burn
                    total_gmt_burned_users += r_gmt_burn
                    daily_sneakers_minted += r_mint

            # --- クラシックGMTアーニング ---
            classic_earners = seg_dau * seg.gmt_earner_ratio * (1 - seg.has_rainbow)
            total_gmt_earned_classic += classic_earners  # 比率で後で分配

            # --- レインボーGMTアーニング ---
            rainbow_earners = seg_dau * seg.has_rainbow
            total_gmt_earned_rainbow += rainbow_earners

            # --- エンハンス ---
            enhancers = seg_dau * params.rainbow.daily_enhance_rate
            shoes_consumed = enhancers * params.rainbow.shoes_consumed_per_enhance
            daily_sneakers_enhanced += shoes_consumed
            # 虹靴排出
            rainbow_prob = params.rainbow.enhance_prob_common  # 簡略化
            new_rainbow = enhancers * rainbow_prob
            daily_rainbow_created += new_rainbow
            # エンハンスによるGST/GMTバーン
            total_gst_burned += enhancers * params.rainbow.enhance_avg_gst
            total_gmt_burned_users += enhancers * params.rainbow.enhance_avg_gmt

            # --- ミステリーボックス ---
            mb_receivers = seg_dau * seg.mb_drop_rate
            if mb_receivers > 0.01:
                mb_lv = min(int(round(seg.avg_mb_level)), 10)
                mb_lv = max(1, mb_lv)
                # 開封コスト (GSTバーン)
                # 注: 高レベルMB(Lv6+)は開封コストが非常に高いため、
                # 実際にはLv6+を開封せず放置or売却するプレイヤーも多い。
                # シミュレーションでは全員開封する前提。
                open_cost = MB_OPENING_COST_GST.get(mb_lv, 5) * mb_receivers
                daily_mb_gst_cost += open_cost
                total_gst_burned += open_cost
                daily_mb_opened += mb_receivers
                # ルートテーブルからジェム・スクロール獲得
                avg_gems, avg_scrolls = MB_LOOT_TABLE.get(mb_lv, (0.3, 0.2))
                gems_from_mb = mb_receivers * avg_gems
                scrolls_from_mb = mb_receivers * avg_scrolls
                daily_mb_gems_created += gems_from_mb
                daily_mb_scrolls_created += scrolls_from_mb
                # ジェムをMBレベル別のジェムレベル確率で振り分け
                gem_probs = MB_GEM_LEVEL_PROB.get(mb_lv, {1: 1.0})
                for gem_lv, prob in gem_probs.items():
                    if prob > 0:
                        mb_gems_by_level[gem_lv] = mb_gems_by_level.get(gem_lv, 0) + gems_from_mb * prob
                # スクロールをレアリティ別に在庫追加
                scroll_rarity_dist = MB_SCROLL_RARITY.get(mb_lv, {"Common": 1.0})
                for sr, sp in scroll_rarity_dist.items():
                    scroll_inventory[sr] += scrolls_from_mb * sp

        # --- GMTプール分配（比率で按分） ---
        # クラシック: classic_earner数に比例して分配
        if total_gmt_earned_classic > 0:
            gmt_classic_earned = gmt_classic_pool  # プール全量を参加者で分配
        else:
            gmt_classic_earned = 0.0

        # レインボー: rainbow_earner数に比例して分配
        if total_gmt_earned_rainbow > 0:
            gmt_rainbow_earned = gmt_rainbow_pool
        else:
            gmt_rainbow_earned = 0.0
            gmt_pool_remaining += gmt_rainbow_pool  # 未消化分はプールに戻す

        total_gmt_earned = gmt_classic_earned + gmt_rainbow_earned

        # --- レルム別結果格納 ---
        for rname in params.realms:
            gst_supply[rname] += realm_gst_minted_map[rname] - realm_gst_burned_map[rname]
            rec[f"{rname}_users"] = realm_users_map[rname]
            rec[f"{rname}_gst_minted"] = realm_gst_minted_map[rname]
            rec[f"{rname}_gst_burned"] = realm_gst_burned_map[rname]
            rec[f"{rname}_gst_supply"] = gst_supply[rname]

        # --- GMT全体更新 ---
        gmt_protocol_burn = params.gmt_monthly_burn / 30.0 if day % 30 != 0 else 0
        gmt_unlock = params.gmt_monthly_unlock / 30.0
        gmt_circulating += (gmt_unlock - gmt_protocol_burn
                            - total_gmt_burned_users + total_gmt_earned)
        gmt_circulating = max(0, min(gmt_circulating, GMT_TOTAL_SUPPLY))

        # --- スクロール消費によるミント制限 ---
        # ミント1回 = スクロール2枚。スクロール在庫不足ならミント数を制限
        # スクロールはレアリティ一致が必要だが、簡略化として全在庫合計で判定
        total_scrolls = sum(scroll_inventory.values())
        max_mints_from_scrolls = total_scrolls / SCROLLS_PER_MINT
        if daily_sneakers_minted > max_mints_from_scrolls:
            # スクロール不足分は実行できない → 実際のミント数を制限
            actual_mints = max_mints_from_scrolls
        else:
            actual_mints = daily_sneakers_minted
        daily_scrolls_used = actual_mints * SCROLLS_PER_MINT
        # スクロール消費（レアリティ比率で按分消費）
        if total_scrolls > 0 and daily_scrolls_used > 0:
            for sr in scroll_inventory:
                consume_ratio = scroll_inventory[sr] / total_scrolls
                scroll_inventory[sr] = max(0, scroll_inventory[sr]
                                           - daily_scrolls_used * consume_ratio)
        daily_sneakers_minted = actual_mints

        # --- スニーカー更新（レアリティ別） ---
        # ミントはレアリティ分布に従う
        for rarity, ratio in params.user_dist.rarity_distribution.items():
            sneakers_by_rarity[rarity] += daily_sneakers_minted * ratio
        # エンハンスはCommon/Uncommonが多く消費される (低レアリティ優先)
        enhance_consume_weights = {"Common": 0.50, "Uncommon": 0.30, "Rare": 0.15,
                                   "Epic": 0.04, "Legendary": 0.01}
        for rarity, w in enhance_consume_weights.items():
            consumed = daily_sneakers_enhanced * w
            sneakers_by_rarity[rarity] = max(0, sneakers_by_rarity[rarity] - consumed)
        total_sneakers = sum(sneakers_by_rarity.values())
        total_sneakers = max(total_sneakers, 1000)

        rainbow_supply += daily_rainbow_created
        # 虹靴HP減衰（HP=0で退役）
        rainbow_retired = rainbow_supply * params.rainbow.rainbow_hp_decay_per_day
        rainbow_supply = max(0, rainbow_supply - rainbow_retired)

        # --- ジェム経済 ---
        # MBからの新規ジェム供給を在庫に追加
        for gem_lv, count in mb_gems_by_level.items():
            if count > 0:
                gems_by_level[gem_lv] = gems_by_level.get(gem_lv, 0) + count

        gem_upgraders = dau * DAILY_GEM_UPGRADE_RATE
        gem_gst_burned = 0.0
        gem_gmt_burned = 0.0
        gems_destroyed = 0.0
        gems_created = 0.0
        for lv in range(1, 9):
            # 各レベルのアップグレード試行数 (低レベルほど多い)
            lv_share = GEM_LEVEL_DISTRIBUTION.get(lv, 0)
            trials = gem_upgraders * lv_share  # 保有比率に応じた試行数
            if trials < 0.001:
                continue
            gst_cost, gmt_cost = GEM_UPGRADE_COST.get(lv, (0, 0))
            success_rate = GEM_UPGRADE_SUCCESS_RATE.get(lv, 1.0)
            successes = trials * success_rate
            failures = trials - successes
            # コスト (試行ごとに発生)
            gem_gst_burned += trials * gst_cost
            gem_gmt_burned += trials * gmt_cost
            # 成功: 3個消費→1個生成 (net -2)
            gems_by_level[lv] = max(0, gems_by_level[lv] - successes * 3)
            gems_by_level.setdefault(lv + 1, 0)
            gems_by_level[lv + 1] += successes
            gems_created += successes
            # 失敗: 3個消失
            gems_by_level[lv] = max(0, gems_by_level[lv] - failures * 3)
            gems_destroyed += failures * 3

        total_gst_burned += gem_gst_burned
        total_gmt_burned_users += gem_gmt_burned
        total_gems = sum(gems_by_level.values())

        # --- 集計 ---
        gst_net = total_gst_minted - total_gst_burned
        total_gst_supply = sum(gst_supply.values())

        rec.update({
            "total_gst_minted": total_gst_minted,
            "total_gst_burned": total_gst_burned,
            "gst_net": gst_net,
            "gst_total_supply": total_gst_supply,
            "gst_daily_inflation_rate": gst_net / max(total_gst_supply, 1),
            # GMT
            "gmt_earned_classic": gmt_classic_earned,
            "gmt_earned_rainbow": gmt_rainbow_earned,
            "total_gmt_earned": total_gmt_earned,
            "gmt_burned_by_users": total_gmt_burned_users,
            "gmt_protocol_burn": gmt_protocol_burn,
            "gmt_circulating": gmt_circulating,
            "gmt_unlock": gmt_unlock,
            "gmt_pool_remaining": gmt_pool_remaining,
            "gmt_daily_emission": actual_gmt_emission,
            # スニーカー
            "total_sneakers": total_sneakers,
            "sneakers_minted_daily": daily_sneakers_minted,
            "sneakers_enhanced_daily": daily_sneakers_enhanced,
            "sneaker_inflation_daily": (daily_sneakers_minted - daily_sneakers_enhanced)
                                       / max(total_sneakers, 1),
            # レアリティ別スニーカー
            **{f"sneakers_{r}": sneakers_by_rarity[r] for r in rarity_names},
            # 虹靴
            "rainbow_supply": rainbow_supply,
            "rainbow_created_daily": daily_rainbow_created,
            "rainbow_retired_daily": rainbow_retired,
            # ミステリーボックス
            "mb_opened_daily": daily_mb_opened,
            "mb_gst_cost": daily_mb_gst_cost,
            "mb_gems_created": daily_mb_gems_created,
            "mb_scrolls_created": daily_mb_scrolls_created,
            "scrolls_used_daily": daily_scrolls_used,
            "scroll_inventory": sum(scroll_inventory.values()),
            # ジェム経済
            "total_gems": total_gems,
            "gem_gst_burned": gem_gst_burned,
            "gem_gmt_burned": gem_gmt_burned,
            "gems_created": gems_created + daily_mb_gems_created,
            "gems_destroyed": gems_destroyed,
            **{f"gems_lv{lv}": gems_by_level.get(lv, 0) for lv in range(1, 10)},
            # GMTアーナー数
            "classic_earners": total_gmt_earned_classic,
            "rainbow_earners": total_gmt_earned_rainbow,
        })
        records.append(rec)

    df = pd.DataFrame(records)
    for col in ["total_gst_minted", "total_gst_burned", "gst_net"]:
        df[f"{col}_7d"] = df[col].rolling(7, min_periods=1).mean()
    df["gst_monthly_inflation"] = df.groupby("month")["gst_net"].transform("sum")
    return df


# ============================================================
# 分析ヘルパー
# ============================================================

def calc_burn_breakdown(df: pd.DataFrame, params: SimParams) -> pd.DataFrame:
    total_burned = df["total_gst_burned"].sum()
    label_map = {
        "level_up": "レベルアップ", "gem_upgrade": "ジェムアップグレード",
        "repair": "修理・HP回復", "mint": "スニーカーミント",
        "socket": "ソケット解放", "enhance": "エンハンス",
        "gst_cap_burn": "GSTキャップ解放", "other": "その他",
    }
    rows = [{"category": k, "ratio": v, "total_gst": total_burned * v,
             "label": label_map.get(k, k)}
            for k, v in params.gst_burn_ratio_map.items()]
    return pd.DataFrame(rows)


def calc_user_asset_distribution(
    total_users: float, user_dist: UserDistribution,
    realm_params: Dict[str, RealmParams],
) -> pd.DataFrame:
    rows = []
    for seg in user_dist.segments:
        n_users = total_users * seg.user_ratio
        cap = seg.energy_capacity
        consumed = seg.energy_consumed
        uncapped_gst = consumed * 10.0
        capped_gst = min(uncapped_gst, seg.gst_cap_level)
        rows.append({
            "category": seg.label, "n_realms": seg.n_realms,
            "sneakers_per_realm": seg.sneakers_per_realm,
            "total_sneakers": seg.total_sneakers,
            "user_ratio": seg.user_ratio, "user_count": n_users,
            "energy_capacity": cap,
            "consumption_rate": seg.energy_consumption_rate,
            "energy_consumed": consumed,
            "walk_minutes": consumed * 5,
            "gst_cap": seg.gst_cap_level,
            "daily_gst_uncapped": uncapped_gst,
            "daily_gst_capped": capped_gst,
            "monthly_gst_earn": capped_gst * 30,
            "has_rainbow": seg.has_rainbow,
            "gmt_earner_ratio": seg.gmt_earner_ratio,
        })
    return pd.DataFrame(rows)


def calc_sneaker_economy(total_sneakers, user_dist, gmt_price):
    rows = []
    for rarity, ratio in user_dist.rarity_distribution.items():
        count = total_sneakers * ratio
        floor_gmt = {"Common": 90, "Uncommon": 297, "Rare": 800,
                     "Epic": 3000, "Legendary": 15000}.get(rarity, 90)
        rows.append({"rarity": rarity, "ratio": ratio, "count": count,
                     "floor_gmt": floor_gmt, "floor_usd": floor_gmt * gmt_price,
                     "total_value_usd": count * floor_gmt * gmt_price})
    return pd.DataFrame(rows)


def calc_levelup_cost_table():
    rows, cum_gst, cum_gmt = [], 0, 0
    for level, (gst, gmt) in LEVEL_UP_COST.items():
        cum_gst += gst; cum_gmt += gmt
        rows.append({"from_level": level, "to_level": level + 1,
                     "gst_cost": gst, "gmt_cost": gmt,
                     "cumulative_gst": cum_gst, "cumulative_gmt": cum_gmt})
    return pd.DataFrame(rows)


def calc_gem_economy_table():
    """ジェムレベル別の経済テーブルを生成"""
    rows = []
    cum_gst, cum_gmt, cum_gems = 0, 0, 0
    for lv in range(1, 10):
        attr = GEM_ATTRIBUTE_BONUS.get(lv, 0)
        awakening = GEM_AWAKENING_PERCENT.get(lv, 0)
        floor_gmt = GEM_FLOOR_PRICE_GMT.get(lv, 0)
        dist = GEM_LEVEL_DISTRIBUTION.get(lv, 0)
        gst_cost, gmt_cost = GEM_UPGRADE_COST.get(lv, (0, 0))
        success = GEM_UPGRADE_SUCCESS_RATE.get(lv, 0)
        # Lv1からこのレベルまでの累積コスト (3^(lv-1)個のLv1が必要)
        gems_needed = 3 ** (lv - 1) if lv > 1 else 1
        rows.append({
            "level": lv,
            "name": ["", "Chipped", "Flawed", "Regular", "Glossy",
                     "Flawless", "Radiant", "Luminous", "Immaculate", "Enchanted"][lv],
            "attribute_bonus": attr,
            "awakening_pct": awakening,
            "upgrade_gst": gst_cost,
            "upgrade_gmt": gmt_cost,
            "success_rate": success if lv < 9 else None,
            "floor_gmt": floor_gmt,
            "floor_usd": floor_gmt * GMT_PRICE,
            "distribution": dist,
            "lv1_gems_needed": gems_needed,
        })
    return pd.DataFrame(rows)


# ============================================================
# データソース参照表
# ============================================================

DATA_SOURCES = {
    "energy_system": {
        "source": "STEPN Whitepaper - Energy System",
        "url": "https://whitepaper.stepn.com/running-module/energy-system",
        "note": "スニーカー数→エナジー割当表、レアリティボーナス",
    },
    "gst_earning": {
        "source": "STEPN Whitepaper - GST Earning / Cap",
        "url": "https://whitepaper.stepn.com/earning-module/gst-cap-mechanics",
        "note": "基本300 GST/日キャップ、GMT Burnで最大2300まで解放",
    },
    "gmt_earning_pool": {
        "source": "STEPN Whitepaper - GMT Earning + P2E報道",
        "url": "https://whitepaper.stepn.com/earning-module/gmt-earning",
        "note": "共通プール分配方式。クラシック40%+虹60%。2026-01-01半減期",
    },
    "gmt_halving": {
        "source": "TradingView - GMT Halving Report",
        "url": "https://www.tradingview.com/news/coinmarketcal:d63053986094b:0-stepn-gmt-gmt-earnings-halving-01-january-2026/",
        "note": "2026年1月1日に初回半減期。日次排出量が50%削減",
    },
    "rainbow_sneakers": {
        "source": "PlayToEarn - Rainbow Sneakers Report",
        "url": "https://playtoearn.com/news/stepn-reveals-new-ways-to-earn-gmt-with-the-introduction-of-rainbow-sneakers",
        "note": "虹靴: Trainer型、最低6E、HP回復不可、GMT専用アーニング",
    },
    "enhancement": {
        "source": "STEPN Whitepaper - Enhancement System",
        "url": "https://whitepaper.stepn.com/game-module/enhancement-system",
        "note": "5足→1足エンハンス。DEC(Dynamic Enhancement Cost)でGST/GMT比依存。"
                "Common: 360GST+40GMT, Uncommon: 1080GST+120GMT, Rare: 2160GST+240GMT。"
                "Uncommonは虹靴排出率5倍（vs Common）",
    },
    "minting": {
        "source": "STEPN Mint Calculator / ipaddressguide.org",
        "url": "https://stepn.vanxh.dev/",
        "note": "ミントコスト: Common 0-mint 120GST+80GMT, Uncommon 480GST+320GMT, "
                "Rare 1440GST+960GMT。ミント回数増で1.2〜3.0倍。DMC(Dynamic Mint Cost)",
    },
    "gem_system": {
        "source": "STEPN Whitepaper - Gems & Sockets",
        "url": "https://whitepaper.stepn.com/game-fi-elements/gems-and-sockets",
        "note": "4タイプ(Efficiency/Luck/Comfort/Resilience)×9レベル。"
                "3個同タイプ同レベル合成→1個上位。Lv4以上でGMT必要。"
                "成功率: Lv1→2:35%, Lv2→3:55%, Lv3→4:65%, Lv4→5:75%, Lv5→6:85%, Lv6+:100%",
    },
    "gem_upgrade": {
        "source": "STEPN Whitepaper - Gem Upgrade + ktrainUSA Twitter",
        "url": "https://whitepaper.stepn.com/game-module/gem-upgrade",
        "note": "アップグレードコスト: Lv1→2:50GST, Lv2→3:100GST, Lv3→4:200GST, "
                "Lv4→5:400GST+100GMT, Lv5→6:800GST+200GMT。失敗時はジェム消失",
    },
    "gmt_pool_split": {
        "source": "P2E.game - STEPN GMT Earning Plans",
        "url": "https://www.p2e.game/dailyNews/3yxsqqbpxb8v",
        "note": "Classic Pool 40% / Rainbow Pool 60%",
    },
    "floor_price": {
        "source": "STEPN-MARKET.GUIDE",
        "url": "https://stepn-market.guide/",
        "date": "2026-03",
        "note": "Common ~90 GMT, Rainbow ~88,888 GMT, 虹靴16リスティング（流通推定50足）",
    },
    "gst_price_sol": {
        "source": "CoinGecko - GST (SOL)",
        "url": "https://www.coingecko.com/en/coins/green-satoshi-token",
        "date": "2026-03", "value": "$0.00175",
    },
    "gmt_tokenomics": {
        "source": "MEXC - GMT Tokenomics",
        "url": "https://www.mexc.com/price/gmt/tokenomics",
        "note": "総供給6B、ユーザー配分30%=1.8B、流通4.27B (2026-03)",
    },
    "mau_data": {
        "source": "Binance Square / REVOX",
        "url": "https://www.binance.com/en/square/post/283349",
        "note": "2023年2月 MAU 42,965、ピーク705,452 (2022-05)",
    },
    "dune_analytics": {
        "source": "Dune Analytics - STEPN Core Metrics",
        "url": "https://dune.com/nguyentoan/STEPN-(GMT,-GST)-Core-Metrics",
        "note": "オンチェーンデータ（取引量、ユーザー数、GMT流入出）",
    },
    "mystery_box": {
        "source": "STEPN Whitepaper + コミュニティデータ集約",
        "url": "https://whitepaper.stepn.com/earning-module/mystery-box-system",
        "note": "MB10レベル。Luck×Energyで品質決定。"
                "開封ベースコスト: Lv1=5GST, Lv2=7, Lv3=10, Lv4=35, Lv5=100, "
                "Lv6=255, Lv7=523, Lv8=1024, Lv9=1818, Lv10=2699GST。"
                "待機時間: Lv1=2日〜Lv10=18日。"
                "ジェム: Lv5+でLv2ジェム確定、Lv9+でLv3ジェム確定。"
                "出典: 黒ブタ(blackpigtail.com), パレゾウ(@parezoparezo), "
                "Otty(@OttySTEPNer1), stepn-market.guide",
    },
    "mint_scroll": {
        "source": "STEPN Whitepaper - Minting Scrolls",
        "url": "https://whitepaper.stepn.com/game-fi-elements/shoe-minting",
        "note": "ミント1回にスクロール2枚必要(レアリティ一致)。"
                "MB Lv2以上からドロップ。スクロールは消費財(ミント後焼却)",
    },
}
