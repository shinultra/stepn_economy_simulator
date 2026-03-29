"""
STEPN OG Economy Simulator v2 - Streamlit Dashboard
=====================================================
全3レルム（Solana / BNB / Polygon）対応、最大4年間の経済シミュレーション。
GSTキャップ、GMTプール（クラシック/虹）、虹靴エンハンス、半減期を可視化。
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

from stepn_engine import (
    SimParams, RealmParams, UserDistribution, UserSegment, DEFAULT_SEGMENTS,
    GmtPoolParams, RainbowParams,
    simulate, calc_burn_breakdown, calc_user_asset_distribution,
    calc_sneaker_economy, calc_levelup_cost_table, calc_gem_economy_table,
    ENERGY_TABLE, RARITY_ENERGY_BONUS, DATA_SOURCES,
    GST_BURN_RATIO, GMT_TOTAL_SUPPLY,
    GST_DAILY_CAP_BASE, GST_DAILY_CAP_MAX,
    GMT_DAILY_EMISSION_POST_HALVING, GMT_POOL_CLASSIC_RATIO, GMT_POOL_RAINBOW_RATIO,
    ENHANCE_RAINBOW_PROB_COMMON, ENHANCE_RAINBOW_PROB_UNCOMMON, ENHANCE_COST,
    MINT_COST, MINT_COUNT_MULTIPLIER_AVG,
    MB_OPENING_COST_GST, MB_GEM_LEVEL_PROB, MB_LOOT_TABLE, MB_SCROLL_RARITY,
    SCROLLS_PER_MINT,
    GEM_TYPES, GEM_ATTRIBUTE_BONUS, GEM_UPGRADE_COST, GEM_UPGRADE_SUCCESS_RATE,
    GEM_FLOOR_PRICE_GMT, GEM_LEVEL_DISTRIBUTION,
    PEAK_MAU, MAU_2023_FEB, ESTIMATED_MAU_2026,
    GST_PRICE_SOL, GST_PRICE_BSC, GST_PRICE_POL, GMT_PRICE,
)

# ============================================================
# Page Config
# ============================================================
st.set_page_config(
    page_title="STEPN OG Economy Simulator v2",
    page_icon="👟",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Custom CSS
# ============================================================
st.markdown("""
<style>
    .stMetric { background: linear-gradient(135deg, #1a1a2e, #16213e);
                padding: 12px 16px; border-radius: 10px; border: 1px solid #333; }
    .stMetric label { color: #aaa !important; font-size: 12px !important; }
    .stMetric [data-testid="stMetricValue"] { color: #fff !important; }
    div[data-testid="stExpander"] { border: 1px solid #333; border-radius: 8px; }
    .source-tag { background: #2a2a3e; color: #8be9fd; padding: 2px 8px;
                  border-radius: 4px; font-size: 11px; font-family: monospace; }
</style>
""", unsafe_allow_html=True)

REALM_COLORS = {"Solana": "#9945FF", "BNB": "#F0B90B", "Polygon": "#8247E5"}
RARITY_COLORS = {
    "Common": "#888", "Uncommon": "#4CAF50", "Rare": "#2196F3",
    "Epic": "#9C27B0", "Legendary": "#FF9800",
}

# ============================================================
# Sidebar - Parameters
# ============================================================
st.sidebar.title("👟 STEPN OG Simulator v2")
st.sidebar.caption("GSTキャップ / GMTプール / 虹靴対応")

# --- シミュレーション設定 ---
with st.sidebar.expander("📅 シミュレーション設定", expanded=True):
    sim_days = st.slider("シミュレーション期間（日）", 30, 1460, 365, step=30,
                         help="最大4年 = 1,460日")
    sim_years = sim_days / 365
    st.caption(f"≈ {sim_years:.1f} 年間")

# --- ユーザー数 ---
with st.sidebar.expander("👥 ユーザーパラメータ", expanded=True):
    st.caption(f"📊 根拠: MAU 42,965 (2023/02, Binance Square)")
    total_users = st.number_input("総ユーザー数 (MAU)", 1000, 1_000_000,
                                   ESTIMATED_MAU_2026, step=1000)
    daily_active_ratio = st.slider("DAU/MAU比率", 0.1, 1.0, 0.60, 0.05)
    monthly_new = st.number_input("月次新規ユーザー", 0, 100_000, 500, step=100)
    monthly_churn = st.slider("月次離脱率", 0.0, 0.30, 0.05, 0.01)

# --- レルム別設定 ---
with st.sidebar.expander("🌐 レルム別パラメータ", expanded=False):
    st.caption("📊 根拠: Dune Analytics, CoinGecko (2026/03)")
    realm_params = {}
    tabs_realm = st.tabs(["Solana", "BNB", "Polygon"])

    defaults = {
        "Solana":  {"share": 0.70, "gst_p": GST_PRICE_SOL, "floor": 90.0,
                    "sneakers": 3.5, "energy": 5.0, "gst_e": 5.0,
                    "gmt_e": 0.03, "gmt_r": 0.05},
        "BNB":     {"share": 0.20, "gst_p": GST_PRICE_BSC, "floor": 120.0,
                    "sneakers": 4.0, "energy": 5.5, "gst_e": 5.0,
                    "gmt_e": 0.02, "gmt_r": 0.03},
        "Polygon": {"share": 0.10, "gst_p": GST_PRICE_POL, "floor": 200.0,
                    "sneakers": 5.0, "energy": 7.0, "gst_e": 5.0,
                    "gmt_e": 0.04, "gmt_r": 0.08},
    }

    for tab, (rname, d) in zip(tabs_realm, defaults.items()):
        with tab:
            share = st.slider(f"ユーザー比率", 0.0, 1.0, d["share"], 0.05,
                              key=f"{rname}_share")
            gst_price = st.number_input(f"GST価格 (USD)", 0.0001, 1.0,
                                         d["gst_p"], 0.0001, format="%.4f",
                                         key=f"{rname}_gst_p")
            floor = st.number_input(f"フロアプライス (GMT)", 1.0, 50000.0,
                                     d["floor"], 10.0, key=f"{rname}_floor")
            avg_snk = st.slider(f"平均スニーカー数/ユーザー", 1.0, 30.0,
                                d["sneakers"], 0.5, key=f"{rname}_snk")
            avg_eng = st.slider(f"平均エナジー/ユーザー", 1.0, 20.0,
                                d["energy"], 0.5, key=f"{rname}_eng")
            gst_earn = st.number_input(f"基本GST/エナジー", 1.0, 20.0,
                                        d["gst_e"], 0.5, key=f"{rname}_gst_e")
            gmt_earn = st.number_input(f"GMT/エナジー (Lv30+)", 0.001, 1.0,
                                        d["gmt_e"], 0.005, format="%.3f",
                                        key=f"{rname}_gmt_e")
            gmt_ratio = st.slider(f"Lv30+比率", 0.0, 0.50, d["gmt_r"], 0.01,
                                   key=f"{rname}_gmt_r")
            realm_params[rname] = RealmParams(
                name=rname, user_share=share, gst_price=gst_price,
                sneaker_floor_gmt=floor, avg_sneakers_per_user=avg_snk,
                avg_energy_per_user=avg_eng, base_gst_per_energy=gst_earn,
                gmt_earn_per_energy=gmt_earn, gmt_earner_ratio=gmt_ratio,
            )

# --- ユーザーセグメント分布 ---
with st.sidebar.expander("📊 ユーザーセグメント分布", expanded=False):
    st.caption("📊 エナジー「キャパシティ」と「消化率」を分離。"
               "GSTキャップ・虹靴保有率もセグメント別に設定可能")

    edited_segments = []
    for i, seg in enumerate(DEFAULT_SEGMENTS):
        st.markdown(f"**{seg.label}**")
        c1, c2, c3 = st.columns(3)
        with c1:
            ratio = st.slider(
                "比率", 0.0, 0.50, seg.user_ratio, 0.01,
                key=f"seg_r_{i}",
                help=f"キャパ {seg.energy_capacity:.0f}E, {seg.energy_capacity*5:.0f}分/日")
        with c2:
            cons = st.slider(
                "消化率", 0.0, 1.0, seg.energy_consumption_rate, 0.05,
                key=f"seg_c_{i}",
                help=f"消化率{seg.energy_consumption_rate:.0%}→実質{seg.energy_consumed:.1f}E")
        with c3:
            cap = st.number_input(
                "GSTキャップ", 300, 2300, int(seg.gst_cap_level), step=100,
                key=f"seg_cap_{i}",
                help=f"GST日次上限 (基本300, GMT Burnで最大2300)")
        # 虹靴保有率
        rainbow = st.slider(
            "虹靴保有率", 0.0, 1.0, seg.has_rainbow, 0.01,
            key=f"seg_rb_{i}",
            help="このセグメントの虹靴保有率")
        edited_segments.append(UserSegment(
            label=seg.label,
            n_realms=seg.n_realms,
            sneakers_per_realm=seg.sneakers_per_realm,
            user_ratio=ratio,
            energy_consumption_rate=cons,
            gmt_earner_ratio=seg.gmt_earner_ratio,
            daily_mint_ratio=seg.daily_mint_ratio,
            gst_cap_level=float(cap),
            has_rainbow=rainbow,
            mb_drop_rate=seg.mb_drop_rate,
            avg_mb_level=seg.avg_mb_level,
        ))

    st.divider()
    st.caption("レアリティ分布")
    r_common = st.slider("Common", 0.0, 1.0, 0.70, 0.05)
    r_uncommon = st.slider("Uncommon", 0.0, 1.0, 0.20, 0.05)
    r_rare = st.slider("Rare", 0.0, 1.0, 0.07, 0.01)
    r_epic = st.slider("Epic", 0.0, 1.0, 0.025, 0.005)
    r_legendary = st.slider("Legendary", 0.0, 1.0, 0.005, 0.001)
    rarity_dist = {
        "Common": r_common, "Uncommon": r_uncommon, "Rare": r_rare,
        "Epic": r_epic, "Legendary": r_legendary,
    }

# --- GMTプール設定 ---
with st.sidebar.expander("🏊 GMTアーニングプール", expanded=False):
    st.caption("📊 出典: Whitepaper + TradingView半減期情報")
    gmt_daily_emission = st.number_input(
        "日次排出量 (GMT/日)", 100_000, 5_000_000,
        GMT_DAILY_EMISSION_POST_HALVING, step=50_000, format="%d",
        help="2026-01-01半減後: 500,000 GMT/日")
    gmt_classic_ratio = st.slider(
        "クラシックプール比率", 0.0, 1.0, GMT_POOL_CLASSIC_RATIO, 0.05,
        help="通常靴Lv30+のGMT earning")
    gmt_rainbow_ratio = 1.0 - gmt_classic_ratio
    st.caption(f"レインボープール比率: {gmt_rainbow_ratio:.0%}")
    gmt_next_halving = st.number_input(
        "次回半減期 (シミュ開始からの日数)", 365, 3650, 1095, step=30,
        help="2026-01-01から約3年後")
    gmt_pool_remaining = st.number_input(
        "プール残量 (GMT)", 100_000_000, 1_800_000_000,
        900_000_000, step=50_000_000, format="%d",
        help="半減後の残量推定")

# --- 虹靴パラメータ ---
with st.sidebar.expander("🌈 虹靴 (Rainbow) パラメータ", expanded=False):
    st.caption("📊 出典: Whitepaper Enhancement System + playtoearn.com")
    rb_prob_common = st.number_input(
        "虹靴排出率 (Common)", 0.001, 0.05,
        ENHANCE_RAINBOW_PROB_COMMON, 0.001, format="%.3f",
        help="Common 5足エンハンス→虹靴: 0.5%")
    rb_prob_uncommon = st.number_input(
        "虹靴排出率 (Uncommon)", 0.001, 0.10,
        ENHANCE_RAINBOW_PROB_UNCOMMON, 0.005, format="%.3f",
        help="Uncommon 5足エンハンス→虹靴: 2.5%")
    rb_daily_enhance_rate = st.slider(
        "日次エンハンス実施率 (DAU中)", 0.0, 0.02, 0.002, 0.0005,
        format="%.4f", help="DAU中何%がエンハンスを実施するか")
    # エンハンスコスト（レアリティ別固定、加重平均を表示）
    _enh_gst = sum(ENHANCE_COST[r]["GST"] * p for r, p in
                   [("Common", 0.70), ("Uncommon", 0.20), ("Rare", 0.07), ("Epic", 0.03)])
    _enh_gmt = sum(ENHANCE_COST[r]["GMT"] * p for r, p in
                   [("Common", 0.70), ("Uncommon", 0.20), ("Rare", 0.07), ("Epic", 0.03)])
    st.caption(f"⚙️ エンハンスコスト (レアリティ加重平均): {_enh_gst:.0f} GST + {_enh_gmt:.0f} GMT")
    st.caption("C: 360+40 / U: 1080+120 / R: 2160+240 / E: 4320+480")
    rb_enhance_avg_gst = _enh_gst
    rb_enhance_avg_gmt = _enh_gmt
    rb_hp_decay = st.slider(
        "虹靴HP減衰率/日", 0.001, 0.05, 0.0133, 0.001, format="%.4f",
        help="HP回復不可。実測2〜3ヶ月でHP枯渇 → 1.33%/日 ≈ 75日で退役")
    rb_initial_supply = st.number_input(
        "虹靴初期流通量", 0, 5000, 50, step=10,
        help="2026-03推定: マーケット16リスティング → 全体約50足")
    rb_avg_power = st.number_input(
        "平均Rainbow Power", 10.0, 500.0, 100.0, 10.0)

# --- トークンパラメータ ---
with st.sidebar.expander("💰 トークン・ミント設定", expanded=False):
    gst_init = st.number_input("GST初期供給量", 100_000_000, 10_000_000_000,
                                1_500_000_000, step=100_000_000, format="%d")
    gmt_circ = st.number_input("GMT流通量", 1_000_000_000, 6_000_000_000,
                                4_270_000_000, step=100_000_000, format="%d",
                                help="出典: MEXC (2026/03)")
    eff_attr = st.slider("平均Efficiency属性", 10.0, 200.0, 50.0, 5.0)
    eff_coeff = st.slider("Efficiency係数", 0.01, 0.5, 0.1, 0.01)
    # ミントコストはレアリティ別固定（加重平均を自動算出）
    _rarity_weights = [("Common", 0.70), ("Uncommon", 0.20), ("Rare", 0.07),
                       ("Epic", 0.025), ("Legendary", 0.005)]
    _mint_gst = sum(MINT_COST[r]["GST"] * MINT_COUNT_MULTIPLIER_AVG * w
                    for r, w in _rarity_weights)
    _mint_gmt = sum(MINT_COST[r]["GMT"] * MINT_COUNT_MULTIPLIER_AVG * w
                    for r, w in _rarity_weights)
    st.caption(f"⚙️ ミントコスト (レアリティ加重平均, ×{MINT_COUNT_MULTIPLIER_AVG}): "
               f"{_mint_gst:.0f} GST + {_mint_gmt:.0f} GMT")
    st.caption("C: 120+80 / U: 480+320 / R: 1440+960 (0-mint基準)")
    mint_gst = _mint_gst
    mint_gmt = _mint_gmt
    gmt_monthly_burn = st.number_input("GMT月次バーン", 0, 100_000_000,
                                        2_000_000, step=500_000, format="%d")
    gmt_monthly_unlock = st.number_input("GMT月次アンロック", 0, 100_000_000,
                                          15_000_000, step=1_000_000, format="%d")

# --- GSTバーン比率 ---
with st.sidebar.expander("🔥 GSTバーン内訳比率", expanded=False):
    st.caption("📊 根拠: コミュニティデータ集約推定")
    burn_levelup = st.slider("レベルアップ", 0.0, 1.0, 0.30, 0.025)
    burn_gem = st.slider("ジェムアップグレード", 0.0, 1.0, 0.20, 0.025)
    burn_repair = st.slider("修理・HP回復", 0.0, 1.0, 0.15, 0.025)
    burn_mint = st.slider("ミント", 0.0, 1.0, 0.10, 0.025)
    burn_socket = st.slider("ソケット解放", 0.0, 1.0, 0.05, 0.025)
    burn_enhance = st.slider("エンハンス", 0.0, 1.0, 0.10, 0.025)
    burn_cap = st.slider("GSTキャップ解放", 0.0, 1.0, 0.05, 0.025)
    burn_other = st.slider("その他", 0.0, 1.0, 0.05, 0.005)
    gst_burn_map = {
        "level_up": burn_levelup, "gem_upgrade": burn_gem,
        "repair": burn_repair, "mint": burn_mint,
        "socket": burn_socket, "enhance": burn_enhance,
        "gst_cap_burn": burn_cap, "other": burn_other,
    }


# ============================================================
# Build Params & Run Simulation
# ============================================================
user_dist = UserDistribution(
    segments=edited_segments,
    rarity_distribution=rarity_dist,
)

gmt_pool = GmtPoolParams(
    daily_emission=float(gmt_daily_emission),
    classic_ratio=gmt_classic_ratio,
    rainbow_ratio=gmt_rainbow_ratio,
    next_halving_day=gmt_next_halving,
    pool_remaining=float(gmt_pool_remaining),
)

rainbow_params = RainbowParams(
    enhance_prob_common=rb_prob_common,
    enhance_prob_uncommon=rb_prob_uncommon,
    daily_enhance_rate=rb_daily_enhance_rate,
    enhance_avg_gst=rb_enhance_avg_gst,
    enhance_avg_gmt=rb_enhance_avg_gmt,
    rainbow_hp_decay_per_day=rb_hp_decay,
    rainbow_supply=float(rb_initial_supply),
    avg_rainbow_power=rb_avg_power,
)

params = SimParams(
    n_days=sim_days,
    total_users=total_users,
    monthly_new_users=monthly_new,
    monthly_churn_rate=monthly_churn,
    daily_active_ratio=daily_active_ratio,
    realms=realm_params,
    user_dist=user_dist,
    gmt_pool=gmt_pool,
    rainbow=rainbow_params,
    gst_initial_supply=gst_init,
    gmt_circulating=gmt_circ,
    avg_efficiency_attr=eff_attr,
    efficiency_coefficient=eff_coeff,
    avg_mint_cost_gst=mint_gst,
    avg_mint_cost_gmt=mint_gmt,
    gst_burn_ratio_map=gst_burn_map,
    gmt_monthly_burn=gmt_monthly_burn,
    gmt_monthly_unlock=gmt_monthly_unlock,
)

# キャッシュキー
cache_key = str(params.__dict__)
if "sim_cache_key" not in st.session_state or st.session_state.sim_cache_key != cache_key:
    with st.spinner("シミュレーション実行中..."):
        df = simulate(params)
        st.session_state.sim_result = df
        st.session_state.sim_cache_key = cache_key
else:
    df = st.session_state.sim_result


# ============================================================
# Main Content
# ============================================================
st.title("👟 STEPN OG Economy Simulator v2")
st.caption(f"GSTキャップ / GMTプール（Classic+Rainbow） / 虹靴対応 | "
           f"{sim_days}日間（{sim_years:.1f}年）シミュレーション")

# --- KPIs ---
col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    st.metric("DAU (最終日)", f"{df['dau'].iloc[-1]:,.0f}",
              delta=f"{df['dau'].iloc[-1] - df['dau'].iloc[0]:+,.0f}")
with col2:
    st.metric("GST日次Mint", f"{df['total_gst_minted'].iloc[-1]:,.0f}")
with col3:
    st.metric("GST日次Burn", f"{df['total_gst_burned'].iloc[-1]:,.0f}")
with col4:
    inflation = df['gst_daily_inflation_rate'].iloc[-1] * 100
    st.metric("GST日次インフレ率", f"{inflation:.4f}%")
with col5:
    st.metric("GMT日次排出", f"{df['gmt_daily_emission'].iloc[-1]:,.0f}")
with col6:
    st.metric("虹靴流通量", f"{df['rainbow_supply'].iloc[-1]:,.0f}")

st.divider()

# --- Tabs ---
tab_overview, tab_token, tab_gmt, tab_users, tab_sneakers, tab_mb, tab_gems, tab_data, tab_sources = st.tabs([
    "📈 概要", "💰 GST経済", "🏊 GMT・虹靴",
    "👥 ユーザー・アセット", "👟 スニーカー経済", "📦 MB・スクロール",
    "💎 ジェム経済", "📋 データテーブル", "📚 データソース",
])

# ============================================================
# Tab 1: 概要
# ============================================================
with tab_overview:
    st.subheader("GST Mint / Burn 推移")

    fig_gst = go.Figure()
    fig_gst.add_trace(go.Scatter(
        x=df["day"], y=df["total_gst_minted_7d"],
        name="GST Minted (7d平均)", line=dict(color="#4CAF50", width=2),
    ))
    fig_gst.add_trace(go.Scatter(
        x=df["day"], y=df["total_gst_burned_7d"],
        name="GST Burned (7d平均)", line=dict(color="#f44336", width=2),
    ))
    fig_gst.add_trace(go.Scatter(
        x=df["day"], y=df["gst_net_7d"],
        name="GST Net (7d平均)", line=dict(color="#FFD700", width=1.5, dash="dash"),
        fill="tozeroy", fillcolor="rgba(255,215,0,0.1)",
    ))
    fig_gst.update_layout(
        template="plotly_dark", height=400,
        legend=dict(orientation="h", y=1.12),
        xaxis_title="日数", yaxis_title="GST/日",
    )
    st.plotly_chart(fig_gst, use_container_width=True)

    # ユーザー推移 + GST供給
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("ユーザー数推移")
        fig_users = go.Figure()
        fig_users.add_trace(go.Scatter(
            x=df["day"], y=df["total_users"], name="MAU",
            line=dict(color="#2196F3", width=2),
        ))
        fig_users.add_trace(go.Scatter(
            x=df["day"], y=df["dau"], name="DAU",
            line=dict(color="#03A9F4", width=1.5, dash="dot"),
        ))
        fig_users.update_layout(template="plotly_dark", height=350,
                                 xaxis_title="日数", yaxis_title="ユーザー数")
        st.plotly_chart(fig_users, use_container_width=True)

    with col_b:
        st.subheader("GST総供給量推移")
        fig_supply = go.Figure()
        fig_supply.add_trace(go.Scatter(
            x=df["day"], y=df["gst_total_supply"],
            name="GST総供給", line=dict(color="#FF9800", width=2),
            fill="tozeroy", fillcolor="rgba(255,152,0,0.15)",
        ))
        fig_supply.update_layout(template="plotly_dark", height=350,
                                  xaxis_title="日数", yaxis_title="GST")
        st.plotly_chart(fig_supply, use_container_width=True)

    # レルム別比較
    st.subheader("レルム別 GST Mint比較")
    fig_realm = go.Figure()
    for rname, color in REALM_COLORS.items():
        col_name = f"{rname}_gst_minted"
        if col_name in df.columns:
            fig_realm.add_trace(go.Scatter(
                x=df["day"], y=df[col_name].rolling(7, min_periods=1).mean(),
                name=rname, line=dict(color=color, width=2),
            ))
    fig_realm.update_layout(template="plotly_dark", height=350,
                             legend=dict(orientation="h", y=1.12),
                             xaxis_title="日数", yaxis_title="GST Minted/日")
    st.plotly_chart(fig_realm, use_container_width=True)


# ============================================================
# Tab 2: GST経済
# ============================================================
with tab_token:
    col_t1, col_t2 = st.columns(2)

    with col_t1:
        st.subheader("GSTバーン内訳")
        burn_df = calc_burn_breakdown(df, params)
        fig_burn = px.pie(
            burn_df, values="total_gst", names="label",
            color="label", hole=0.4,
            color_discrete_map={
                "レベルアップ": "#4CAF50", "ジェムアップグレード": "#2196F3",
                "修理・HP回復": "#FF9800", "スニーカーミント": "#9C27B0",
                "ソケット解放": "#f44336", "エンハンス": "#00BCD4",
                "GSTキャップ解放": "#FFEB3B", "その他": "#666",
            },
        )
        fig_burn.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_burn, use_container_width=True)

    with col_t2:
        st.subheader("GST日次インフレ率推移")
        fig_inf = go.Figure()
        infl_7d = df["gst_daily_inflation_rate"].rolling(7, min_periods=1).mean() * 100
        fig_inf.add_trace(go.Scatter(
            x=df["day"], y=infl_7d,
            name="日次インフレ率 (7d平均, %)",
            line=dict(color="#f44336", width=2),
            fill="tozeroy", fillcolor="rgba(244,67,54,0.15)",
        ))
        fig_inf.add_hline(y=0, line_color="#666", line_dash="dash")
        fig_inf.update_layout(template="plotly_dark", height=400,
                               xaxis_title="日数", yaxis_title="インフレ率 (%)")
        st.plotly_chart(fig_inf, use_container_width=True)

    # GSTキャップ解説
    st.subheader("GSTキャップ仕様")
    st.info(f"""
    **GST日次キャップ**: 基本 {GST_DAILY_CAP_BASE} GST/日。
    GMT Burnにより段階的に最大 **{GST_DAILY_CAP_MAX} GST/日** まで解放可能。
    高エナジーユーザーはキャップ解放しないとエナジーを活かしきれない。
    出典: whitepaper.stepn.com/earning-module/gst-cap-mechanics
    """)


# ============================================================
# Tab 3: GMT・虹靴経済 (NEW)
# ============================================================
with tab_gmt:
    st.subheader("GMTアーニングプール")
    st.caption("📊 共通プール分配方式: Classic 40% + Rainbow 60%。2026-01-01初回半減期")

    # GMT流通量 + プール残量
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_gmt = go.Figure()
        fig_gmt.add_trace(go.Scatter(
            x=df["day"], y=df["gmt_circulating"],
            name="GMT流通量", line=dict(color="#FF9800", width=2),
        ))
        fig_gmt.add_hline(y=GMT_TOTAL_SUPPLY, line_dash="dash",
                           annotation_text="GMT上限 (6B)", line_color="#666")
        fig_gmt.update_layout(template="plotly_dark", height=400,
                               xaxis_title="日数", yaxis_title="GMT",
                               title="GMT流通量推移")
        st.plotly_chart(fig_gmt, use_container_width=True)

    with col_g2:
        fig_pool = go.Figure()
        fig_pool.add_trace(go.Scatter(
            x=df["day"], y=df["gmt_pool_remaining"],
            name="プール残量", line=dict(color="#2196F3", width=2),
            fill="tozeroy", fillcolor="rgba(33,150,243,0.15)",
        ))
        fig_pool.update_layout(template="plotly_dark", height=400,
                                xaxis_title="日数", yaxis_title="GMT",
                                title="GMTアーニングプール残量")
        st.plotly_chart(fig_pool, use_container_width=True)

    # Classic vs Rainbow earnings
    st.subheader("GMT日次アーニング: Classic vs Rainbow")
    fig_gmt_earn = go.Figure()
    fig_gmt_earn.add_trace(go.Scatter(
        x=df["day"], y=df["gmt_earned_classic"],
        name="Classic Pool", line=dict(color="#4CAF50", width=2),
        stackgroup="one",
    ))
    fig_gmt_earn.add_trace(go.Scatter(
        x=df["day"], y=df["gmt_earned_rainbow"],
        name="Rainbow Pool", line=dict(color="#FF6F00", width=2),
        stackgroup="one",
    ))
    fig_gmt_earn.add_trace(go.Scatter(
        x=df["day"], y=df["gmt_burned_by_users"],
        name="GMT Burned (Users)", line=dict(color="#f44336", width=1.5, dash="dash"),
    ))
    fig_gmt_earn.update_layout(template="plotly_dark", height=400,
                                legend=dict(orientation="h", y=1.12),
                                xaxis_title="日数", yaxis_title="GMT/日")
    st.plotly_chart(fig_gmt_earn, use_container_width=True)

    # GMT日次フロー詳細
    col_gf1, col_gf2 = st.columns(2)
    with col_gf1:
        st.subheader("GMT日次排出量")
        fig_emission = go.Figure()
        fig_emission.add_trace(go.Scatter(
            x=df["day"], y=df["gmt_daily_emission"],
            name="日次排出量", line=dict(color="#9C27B0", width=2),
        ))
        fig_emission.update_layout(template="plotly_dark", height=350,
                                    xaxis_title="日数", yaxis_title="GMT/日",
                                    title="半減期の影響")
        st.plotly_chart(fig_emission, use_container_width=True)

    with col_gf2:
        st.subheader("GMT Net Flow")
        gmt_net = df["total_gmt_earned"] - df["gmt_burned_by_users"]
        fig_gmt_net = go.Figure()
        fig_gmt_net.add_trace(go.Scatter(
            x=df["day"], y=gmt_net,
            name="GMT Net (Earned - Burned)",
            line=dict(color="#FFD700", width=2),
            fill="tozeroy", fillcolor="rgba(255,215,0,0.1)",
        ))
        fig_gmt_net.add_hline(y=0, line_color="#666", line_dash="dash")
        fig_gmt_net.update_layout(template="plotly_dark", height=350,
                                   xaxis_title="日数", yaxis_title="GMT/日")
        st.plotly_chart(fig_gmt_net, use_container_width=True)

    # --- 虹靴セクション ---
    st.divider()
    st.subheader("🌈 虹靴 (Rainbow Sneakers) 経済")
    st.caption("📊 エンハンス5足→1足、一定確率で虹靴排出。HP回復不可、GMT専用アーニング")

    col_rb1, col_rb2 = st.columns(2)
    with col_rb1:
        fig_rb_supply = go.Figure()
        fig_rb_supply.add_trace(go.Scatter(
            x=df["day"], y=df["rainbow_supply"],
            name="虹靴流通量", line=dict(color="#FF6F00", width=2),
            fill="tozeroy", fillcolor="rgba(255,111,0,0.15)",
        ))
        fig_rb_supply.update_layout(template="plotly_dark", height=350,
                                     xaxis_title="日数", yaxis_title="足",
                                     title="虹靴流通量推移")
        st.plotly_chart(fig_rb_supply, use_container_width=True)

    with col_rb2:
        fig_rb_flow = go.Figure()
        fig_rb_flow.add_trace(go.Bar(
            x=df["day"], y=df["rainbow_created_daily"],
            name="新規排出", marker_color="rgba(76,175,80,0.7)",
        ))
        fig_rb_flow.add_trace(go.Bar(
            x=df["day"], y=-df["rainbow_retired_daily"],
            name="退役 (HP=0)", marker_color="rgba(244,67,54,0.7)",
        ))
        fig_rb_flow.update_layout(template="plotly_dark", height=350,
                                   barmode="relative",
                                   xaxis_title="日数", yaxis_title="足/日",
                                   title="虹靴 日次フロー（排出 vs 退役）")
        st.plotly_chart(fig_rb_flow, use_container_width=True)

    # 虹靴仕様まとめ
    st.info(f"""
    **虹靴仕様**:
    排出確率 Common {ENHANCE_RAINBOW_PROB_COMMON*100:.1f}% / Uncommon {ENHANCE_RAINBOW_PROB_UNCOMMON*100:.1f}% |
    最低6エナジー消費 | HP回復不可 (減衰率 {rb_hp_decay*100:.2f}%/日 ≈ **{int(1/rb_hp_decay)}日で退役**) |
    GMT専用アーニング (Rainbow Pool) | フロア: 88,888 GMT |
    現在マーケット出品: **16足** / 推定流通: **約50足** (2026-03)
    """)


# ============================================================
# Tab 4: ユーザー・アセット分布
# ============================================================
with tab_users:
    st.subheader("ユーザーセグメント分布（GSTキャップ・虹靴反映）")
    st.caption("エナジーキャパシティ × 消化率 × GSTキャップ → 実GST収益を計算")

    asset_df = calc_user_asset_distribution(
        total_users, user_dist, realm_params,
    )

    # --- グラフ1: キャパ vs 実消化 比較 ---
    st.subheader("エナジー: キャパシティ vs 実消化量")
    fig_cap = go.Figure()
    fig_cap.add_trace(go.Bar(
        x=asset_df["category"], y=asset_df["energy_capacity"],
        name="キャパシティ", marker_color="rgba(100,149,237,0.4)",
    ))
    fig_cap.add_trace(go.Bar(
        x=asset_df["category"], y=asset_df["energy_consumed"],
        name="実消化量", marker_color="#4CAF50",
    ))
    fig_cap.update_layout(
        template="plotly_dark", height=450, barmode="overlay",
        xaxis_tickangle=-35, legend=dict(orientation="h", y=1.12),
        yaxis_title="エナジー/日",
    )
    st.plotly_chart(fig_cap, use_container_width=True)

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        fig_dist = px.bar(
            asset_df, x="category", y="user_count",
            text="user_count", color="n_realms",
            labels={"category": "セグメント", "user_count": "ユーザー数",
                    "n_realms": "レルム数"},
            color_discrete_map={1: "#4CAF50", 2: "#FF9800", 3: "#f44336"},
        )
        fig_dist.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
        fig_dist.update_layout(template="plotly_dark", height=450,
                               xaxis_tickangle=-35, title="ユーザー数分布")
        st.plotly_chart(fig_dist, use_container_width=True)

    with col_u2:
        # GSTキャップ vs 未キャップ比較
        fig_gst_cap = go.Figure()
        fig_gst_cap.add_trace(go.Bar(
            x=asset_df["category"], y=asset_df["daily_gst_uncapped"],
            name="GST (キャップなし)", marker_color="rgba(100,149,237,0.4)",
        ))
        fig_gst_cap.add_trace(go.Bar(
            x=asset_df["category"], y=asset_df["daily_gst_capped"],
            name="GST (キャップ適用)", marker_color="#4CAF50",
        ))
        fig_gst_cap.update_layout(
            template="plotly_dark", height=450, barmode="overlay",
            xaxis_tickangle=-35, title="GST日次収益: キャップ効果",
            yaxis_title="GST/日",
        )
        st.plotly_chart(fig_gst_cap, use_container_width=True)

    # --- 詳細テーブル ---
    st.subheader("セグメント詳細")
    st.dataframe(
        asset_df.style.format({
            "user_ratio": "{:.1%}", "user_count": "{:,.0f}",
            "energy_capacity": "{:.0f}", "consumption_rate": "{:.0%}",
            "energy_consumed": "{:.1f}", "walk_minutes": "{:.0f}",
            "gst_cap": "{:,.0f}",
            "daily_gst_uncapped": "{:,.1f}", "daily_gst_capped": "{:,.1f}",
            "monthly_gst_earn": "{:,.0f}",
            "total_sneakers": "{:.0f}",
            "has_rainbow": "{:.1%}",
            "gmt_earner_ratio": "{:.1%}",
        }),
        use_container_width=True,
    )

    # エナジーテーブル
    st.subheader("エナジーシステム参照表")
    st.caption("📊 出典: whitepaper.stepn.com/running-module/energy-system")
    energy_rows = []
    for n, e in sorted(ENERGY_TABLE.items()):
        energy_rows.append({
            "スニーカー数": n, "基本エナジー": e,
            "活動時間(分)": e * 5,
            "基本GST/日": e * 5.0,
        })
    st.dataframe(pd.DataFrame(energy_rows), use_container_width=True)


# ============================================================
# Tab 5: スニーカー経済
# ============================================================
with tab_sneakers:
    st.subheader("スニーカー経済指標")

    sneaker_econ = calc_sneaker_economy(
        df["total_sneakers"].iloc[-1], user_dist, GMT_PRICE,
    )

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        fig_rarity = px.pie(
            sneaker_econ, values="count", names="rarity",
            color="rarity", color_discrete_map=RARITY_COLORS,
            hole=0.4, title="レアリティ別スニーカー分布（最終日）",
        )
        fig_rarity.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_rarity, use_container_width=True)

    with col_s2:
        fig_value = px.bar(
            sneaker_econ, x="rarity", y="total_value_usd",
            color="rarity", color_discrete_map=RARITY_COLORS,
            title="レアリティ別 総価値 (USD)",
            labels={"total_value_usd": "総価値 (USD)", "rarity": "レアリティ"},
        )
        fig_value.update_layout(template="plotly_dark", height=400, showlegend=False)
        st.plotly_chart(fig_value, use_container_width=True)

    st.dataframe(
        sneaker_econ.style.format({
            "ratio": "{:.1%}", "count": "{:,.0f}", "floor_gmt": "{:,.0f}",
            "floor_usd": "${:,.2f}", "total_value_usd": "${:,.0f}",
        }),
        use_container_width=True,
    )

    # レアリティ別スニーカー供給推移
    st.subheader("レアリティ別スニーカー供給推移")
    fig_snk_rarity = go.Figure()
    for rarity, color in RARITY_COLORS.items():
        col_name = f"sneakers_{rarity}"
        if col_name in df.columns:
            fig_snk_rarity.add_trace(go.Scatter(
                x=df["day"], y=df[col_name],
                name=rarity, line=dict(color=color, width=2),
                stackgroup="one",
            ))
    fig_snk_rarity.update_layout(
        template="plotly_dark", height=450,
        legend=dict(orientation="h", y=1.12),
        xaxis_title="日数", yaxis_title="スニーカー数",
    )
    st.plotly_chart(fig_snk_rarity, use_container_width=True)

    # レアリティ別個別推移 (対数スケール)
    col_sn1, col_sn2 = st.columns(2)
    with col_sn1:
        fig_snk_each = go.Figure()
        for rarity, color in RARITY_COLORS.items():
            col_name = f"sneakers_{rarity}"
            if col_name in df.columns:
                fig_snk_each.add_trace(go.Scatter(
                    x=df["day"], y=df[col_name],
                    name=rarity, line=dict(color=color, width=2),
                ))
        fig_snk_each.update_layout(
            template="plotly_dark", height=400,
            yaxis_type="log", yaxis_title="スニーカー数 (対数)",
            xaxis_title="日数", title="レアリティ別推移（対数スケール）",
        )
        st.plotly_chart(fig_snk_each, use_container_width=True)

    with col_sn2:
        fig_snk_flow = go.Figure()
        fig_snk_flow.add_trace(go.Scatter(
            x=df["day"], y=df["sneakers_minted_daily"],
            name="日次ミント", line=dict(color="#4CAF50", width=2),
        ))
        fig_snk_flow.add_trace(go.Scatter(
            x=df["day"], y=df["sneakers_enhanced_daily"],
            name="日次エンハンス消費", line=dict(color="#f44336", width=2),
        ))
        fig_snk_flow.update_layout(template="plotly_dark", height=400,
                                    xaxis_title="日数", yaxis_title="足/日",
                                    title="ミント vs エンハンス消費")
        st.plotly_chart(fig_snk_flow, use_container_width=True)

    # レベルアップコスト
    st.subheader("レベルアップコスト一覧")
    st.caption("📊 出典: wealthquint.com/stepn-level-up-cost, stepn.guide/lvlup")
    lvl_df = calc_levelup_cost_table()
    fig_lvl = go.Figure()
    fig_lvl.add_trace(go.Bar(
        x=lvl_df["to_level"], y=lvl_df["gst_cost"],
        name="GST", marker_color="#4CAF50",
    ))
    fig_lvl.add_trace(go.Bar(
        x=lvl_df["to_level"], y=lvl_df["gmt_cost"],
        name="GMT", marker_color="#FF9800",
    ))
    fig_lvl.add_trace(go.Scatter(
        x=lvl_df["to_level"], y=lvl_df["cumulative_gst"],
        name="累計GST", line=dict(color="#fff", dash="dash"), yaxis="y2",
    ))
    fig_lvl.update_layout(
        template="plotly_dark", height=400, barmode="stack",
        yaxis=dict(title="コスト/レベル"),
        yaxis2=dict(title="累計GST", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig_lvl, use_container_width=True)


# ============================================================
# Tab 6: MB・スクロール経済
# ============================================================
with tab_mb:
    st.subheader("📦 ミステリーボックス & Mint Scroll 経済")
    st.caption("📊 出典: whitepaper.stepn.com/earning-module/mystery-box-system, "
               "コミュニティデータ集約")

    # --- MB日次開封数・GSTコスト ---
    col_mb1, col_mb2 = st.columns(2)
    with col_mb1:
        fig_mb_open = go.Figure()
        fig_mb_open.add_trace(go.Scatter(
            x=df["day"], y=df["mb_opened_daily"],
            name="MB開封数/日", fill="tozeroy",
            line=dict(color="#FF9800"),
        ))
        fig_mb_open.update_layout(
            title="ミステリーボックス日次開封数",
            xaxis_title="Day", yaxis_title="開封数",
            template="plotly_dark", height=350,
        )
        st.plotly_chart(fig_mb_open, use_container_width=True)

    with col_mb2:
        fig_mb_cost = go.Figure()
        fig_mb_cost.add_trace(go.Scatter(
            x=df["day"], y=df["mb_gst_cost"],
            name="MB開封GSTコスト", fill="tozeroy",
            line=dict(color="#F44336"),
        ))
        fig_mb_cost.update_layout(
            title="MB開封コスト (GST Burn)",
            xaxis_title="Day", yaxis_title="GST",
            template="plotly_dark", height=350,
        )
        st.plotly_chart(fig_mb_cost, use_container_width=True)

    # --- MB由来のジェム・スクロール供給 ---
    col_mb3, col_mb4 = st.columns(2)
    with col_mb3:
        fig_mb_gems = go.Figure()
        fig_mb_gems.add_trace(go.Scatter(
            x=df["day"], y=df["mb_gems_created"],
            name="MB由来ジェム/日", fill="tozeroy",
            line=dict(color="#4CAF50"),
        ))
        fig_mb_gems.add_trace(go.Scatter(
            x=df["day"], y=df["mb_gems_created"].cumsum(),
            name="累計", yaxis="y2",
            line=dict(color="#81C784", dash="dash"),
        ))
        fig_mb_gems.update_layout(
            title="MB由来ジェム供給",
            xaxis_title="Day", yaxis_title="日次供給",
            yaxis2=dict(title="累計", overlaying="y", side="right"),
            template="plotly_dark", height=350,
        )
        st.plotly_chart(fig_mb_gems, use_container_width=True)

    with col_mb4:
        fig_mb_scroll = go.Figure()
        fig_mb_scroll.add_trace(go.Scatter(
            x=df["day"], y=df["mb_scrolls_created"],
            name="スクロール生成/日",
            line=dict(color="#2196F3"),
        ))
        fig_mb_scroll.add_trace(go.Scatter(
            x=df["day"], y=df["scrolls_used_daily"],
            name="スクロール消費/日",
            line=dict(color="#FF5722"),
        ))
        fig_mb_scroll.update_layout(
            title="Mint Scroll 生成 vs 消費",
            xaxis_title="Day", yaxis_title="スクロール数/日",
            template="plotly_dark", height=350,
        )
        st.plotly_chart(fig_mb_scroll, use_container_width=True)

    # --- スクロール在庫推移 ---
    col_mb5, col_mb6 = st.columns(2)
    with col_mb5:
        fig_scroll_inv = go.Figure()
        fig_scroll_inv.add_trace(go.Scatter(
            x=df["day"], y=df["scroll_inventory"],
            name="スクロール在庫", fill="tozeroy",
            line=dict(color="#9C27B0"),
        ))
        fig_scroll_inv.update_layout(
            title="Mint Scroll 在庫推移",
            xaxis_title="Day", yaxis_title="在庫数",
            template="plotly_dark", height=350,
        )
        st.plotly_chart(fig_scroll_inv, use_container_width=True)

    with col_mb6:
        # MB仕様テーブル
        st.markdown("#### MBレベル別ルートテーブル")
        mb_spec_rows = []
        for lv in range(1, 6):
            avg_gems, avg_scrolls = MB_LOOT_TABLE.get(lv, (0, 0))
            open_cost = MB_OPENING_COST_GST.get(lv, 5)
            mb_spec_rows.append({
                "MBレベル": lv,
                "開封コスト(GST)": open_cost,
                "平均ジェム数": avg_gems,
                "平均スクロール数": avg_scrolls,
            })
        st.dataframe(pd.DataFrame(mb_spec_rows), use_container_width=True, hide_index=True)

        st.markdown("#### MB内ジェムレベル分布")
        gem_prob_rows = [{"ジェムLv": lv, "確率": f"{prob*100:.1f}%"}
                         for lv, prob in MB_GEM_LEVEL_PROB.items()]
        st.dataframe(pd.DataFrame(gem_prob_rows), use_container_width=True, hide_index=True)

    # --- サマリーメトリクス ---
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("年間MB開封数", f"{df['mb_opened_daily'].sum():,.0f}")
    with m2:
        st.metric("年間MB GST Burn", f"{df['mb_gst_cost'].sum():,.0f}")
    with m3:
        st.metric("年間MB由来ジェム", f"{df['mb_gems_created'].sum():,.0f}")
    with m4:
        st.metric("年間スクロール生成", f"{df['mb_scrolls_created'].sum():,.0f}")


# ============================================================
# Tab 7: ジェム経済
# ============================================================
with tab_gems:
    st.subheader("💎 ジェム経済")
    st.caption("📊 出典: whitepaper.stepn.com/game-fi-elements/gems-and-sockets, "
               "whitepaper.stepn.com/game-module/gem-upgrade")

    # ジェムレベル別推移
    st.subheader("ジェムレベル別流通量推移")
    fig_gems = go.Figure()
    gem_colors = {1: "#aaa", 2: "#4CAF50", 3: "#2196F3", 4: "#9C27B0",
                  5: "#FF9800", 6: "#f44336", 7: "#00BCD4", 8: "#FFD700", 9: "#FF6F00"}
    for lv in range(1, 10):
        col_name = f"gems_lv{lv}"
        if col_name in df.columns:
            fig_gems.add_trace(go.Scatter(
                x=df["day"], y=df[col_name],
                name=f"Lv{lv}", line=dict(color=gem_colors.get(lv, "#888"), width=2),
                stackgroup="one",
            ))
    fig_gems.update_layout(
        template="plotly_dark", height=450,
        legend=dict(orientation="h", y=1.12),
        xaxis_title="日数", yaxis_title="ジェム数",
    )
    st.plotly_chart(fig_gems, use_container_width=True)

    # 個別推移 (対数) + GSTバーン
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig_gem_log = go.Figure()
        for lv in range(1, 7):
            col_name = f"gems_lv{lv}"
            if col_name in df.columns:
                fig_gem_log.add_trace(go.Scatter(
                    x=df["day"], y=df[col_name].clip(lower=1),
                    name=f"Lv{lv}", line=dict(color=gem_colors.get(lv, "#888"), width=2),
                ))
        fig_gem_log.update_layout(
            template="plotly_dark", height=400,
            yaxis_type="log", yaxis_title="ジェム数 (対数)",
            xaxis_title="日数", title="ジェムレベル別推移（Lv1-6）",
        )
        st.plotly_chart(fig_gem_log, use_container_width=True)

    with col_g2:
        fig_gem_burn = go.Figure()
        fig_gem_burn.add_trace(go.Scatter(
            x=df["day"], y=df["gem_gst_burned"],
            name="GST Burned (ジェム)", line=dict(color="#f44336", width=2),
        ))
        fig_gem_burn.add_trace(go.Scatter(
            x=df["day"], y=df["gem_gmt_burned"],
            name="GMT Burned (ジェム)", line=dict(color="#FF9800", width=2),
        ))
        fig_gem_burn.update_layout(
            template="plotly_dark", height=400,
            xaxis_title="日数", yaxis_title="トークン/日",
            title="ジェムアップグレードによるトークンバーン",
        )
        st.plotly_chart(fig_gem_burn, use_container_width=True)

    # ジェム総数 + 生成/消失
    col_g3, col_g4 = st.columns(2)
    with col_g3:
        fig_gem_total = go.Figure()
        fig_gem_total.add_trace(go.Scatter(
            x=df["day"], y=df["total_gems"],
            name="総ジェム数", line=dict(color="#00BCD4", width=2),
            fill="tozeroy", fillcolor="rgba(0,188,212,0.15)",
        ))
        fig_gem_total.update_layout(template="plotly_dark", height=350,
                                     xaxis_title="日数", yaxis_title="ジェム数",
                                     title="総ジェム流通量推移")
        st.plotly_chart(fig_gem_total, use_container_width=True)

    with col_g4:
        fig_gem_flow = go.Figure()
        fig_gem_flow.add_trace(go.Scatter(
            x=df["day"], y=df["gems_created"],
            name="生成 (アップグレード成功)", line=dict(color="#4CAF50", width=2),
        ))
        fig_gem_flow.add_trace(go.Scatter(
            x=df["day"], y=df["gems_destroyed"],
            name="消失 (失敗)", line=dict(color="#f44336", width=2),
        ))
        fig_gem_flow.update_layout(template="plotly_dark", height=350,
                                    xaxis_title="日数", yaxis_title="ジェム/日",
                                    title="日次ジェムフロー")
        st.plotly_chart(fig_gem_flow, use_container_width=True)

    # ジェム仕様テーブル
    st.subheader("ジェムレベル別仕様")
    gem_table = calc_gem_economy_table()
    st.dataframe(
        gem_table.style.format({
            "attribute_bonus": "+{:,.0f}",
            "awakening_pct": "{:,.0f}%",
            "upgrade_gst": "{:,.0f}",
            "upgrade_gmt": "{:,.0f}",
            "success_rate": "{:.0%}",
            "floor_gmt": "{:,.0f}",
            "floor_usd": "${:,.2f}",
            "distribution": "{:.2%}",
            "lv1_gems_needed": "{:,.0f}",
        }, na_rep="-"),
        use_container_width=True,
    )

    # ジェムアップグレードコスト
    st.subheader("アップグレード成功率と累積コスト")
    fig_gem_cost = go.Figure()
    fig_gem_cost.add_trace(go.Bar(
        x=[f"Lv{lv}→{lv+1}" for lv in range(1, 9)],
        y=[GEM_UPGRADE_COST[lv][0] for lv in range(1, 9)],
        name="GST", marker_color="#4CAF50",
    ))
    fig_gem_cost.add_trace(go.Bar(
        x=[f"Lv{lv}→{lv+1}" for lv in range(1, 9)],
        y=[GEM_UPGRADE_COST[lv][1] for lv in range(1, 9)],
        name="GMT", marker_color="#FF9800",
    ))
    fig_gem_cost.add_trace(go.Scatter(
        x=[f"Lv{lv}→{lv+1}" for lv in range(1, 9)],
        y=[GEM_UPGRADE_SUCCESS_RATE.get(lv, 1.0) * 100 for lv in range(1, 9)],
        name="成功率 (%)", line=dict(color="#fff", dash="dash", width=2),
        yaxis="y2",
    ))
    fig_gem_cost.update_layout(
        template="plotly_dark", height=400, barmode="stack",
        yaxis=dict(title="コスト (トークン)"),
        yaxis2=dict(title="成功率 (%)", overlaying="y", side="right",
                    range=[0, 105]),
        legend=dict(orientation="h", y=1.12),
    )
    st.plotly_chart(fig_gem_cost, use_container_width=True)

    st.info("""
    **ジェム仕様まとめ**:
    4タイプ (Efficiency/Luck/Comfort/Resilience) × 9レベル |
    アップグレード: 同タイプ同レベル3個 → 1個上位 (GST+GMT消費) |
    Lv1-5は失敗リスクあり (失敗時ジェム消失) |
    Lv4以上でGMT必要 | GSTバーンの約20%がジェム関連
    """)


# ============================================================
# Tab 7: データテーブル
# ============================================================
with tab_data:
    st.subheader("シミュレーション結果（日次）")

    display_cols = st.multiselect(
        "表示列を選択",
        options=df.columns.tolist(),
        default=["day", "month", "total_users", "dau",
                 "total_gst_minted", "total_gst_burned", "gst_net",
                 "gst_total_supply",
                 "gmt_earned_classic", "gmt_earned_rainbow",
                 "gmt_circulating", "gmt_pool_remaining",
                 "total_sneakers",
                 "sneakers_Common", "sneakers_Uncommon", "sneakers_Rare",
                 "sneakers_Epic", "sneakers_Legendary",
                 "rainbow_supply",
                 "mb_opened_daily", "mb_gst_cost",
                 "mb_gems_created", "mb_scrolls_created",
                 "scroll_inventory", "total_gems",
                 "gem_gst_burned", "gem_gmt_burned"],
    )

    if display_cols:
        format_dict = {
            "total_users": "{:,.0f}", "dau": "{:,.0f}",
            "total_gst_minted": "{:,.0f}", "total_gst_burned": "{:,.0f}",
            "gst_net": "{:,.0f}", "gst_total_supply": "{:,.0f}",
            "gst_daily_inflation_rate": "{:.6f}",
            "gmt_earned_classic": "{:,.0f}", "gmt_earned_rainbow": "{:,.0f}",
            "total_gmt_earned": "{:,.0f}", "gmt_burned_by_users": "{:,.0f}",
            "gmt_circulating": "{:,.0f}", "gmt_pool_remaining": "{:,.0f}",
            "gmt_daily_emission": "{:,.0f}",
            "total_sneakers": "{:,.0f}", "rainbow_supply": "{:,.0f}",
            "rainbow_created_daily": "{:.2f}", "rainbow_retired_daily": "{:.2f}",
            "sneakers_Common": "{:,.0f}", "sneakers_Uncommon": "{:,.0f}",
            "sneakers_Rare": "{:,.0f}", "sneakers_Epic": "{:,.0f}",
            "sneakers_Legendary": "{:,.0f}",
            "mb_opened_daily": "{:,.0f}", "mb_gst_cost": "{:,.0f}",
            "mb_gems_created": "{:,.1f}", "mb_scrolls_created": "{:,.1f}",
            "scroll_inventory": "{:,.0f}",
            "total_gems": "{:,.0f}", "gem_gst_burned": "{:,.0f}",
            "gem_gmt_burned": "{:,.0f}",
        }
        # filter to only existing columns
        active_fmt = {k: v for k, v in format_dict.items() if k in display_cols}
        st.dataframe(
            df[display_cols].style.format(active_fmt, na_rep="-"),
            use_container_width=True, height=500,
        )

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 CSV ダウンロード",
        data=csv,
        file_name="stepn_simulation_v2_result.csv",
        mime="text/csv",
    )

    # 月次サマリー
    st.subheader("月次サマリー")
    monthly_agg = {
        "total_users": "last",
        "dau": "mean",
        "total_gst_minted": "sum",
        "total_gst_burned": "sum",
        "gst_net": "sum",
        "gst_total_supply": "last",
        "gmt_earned_classic": "sum",
        "gmt_earned_rainbow": "sum",
        "gmt_circulating": "last",
        "gmt_pool_remaining": "last",
        "total_sneakers": "last",
        "sneakers_Common": "last",
        "sneakers_Uncommon": "last",
        "sneakers_Rare": "last",
        "sneakers_Epic": "last",
        "sneakers_Legendary": "last",
        "rainbow_supply": "last",
        "sneakers_minted_daily": "sum",
        "mb_opened_daily": "sum",
        "mb_gst_cost": "sum",
        "mb_gems_created": "sum",
        "mb_scrolls_created": "sum",
        "scroll_inventory": "last",
        "total_gems": "last",
        "gem_gst_burned": "sum",
        "gem_gmt_burned": "sum",
    }
    # filter to existing columns
    monthly_agg = {k: v for k, v in monthly_agg.items() if k in df.columns}
    monthly = df.groupby("month").agg(monthly_agg).reset_index()
    monthly.columns = [
        "月", "MAU", "平均DAU", "GST Minted", "GST Burned",
        "GST Net", "GST供給量", "GMT Classic", "GMT Rainbow",
        "GMT流通量", "GMTプール残", "スニーカー総数",
        "Common", "Uncommon", "Rare", "Epic", "Legendary",
        "虹靴数", "新規ミント",
        "MB開封", "MB GST", "MB Gems", "MB Scrolls", "Scroll在庫",
        "総ジェム数", "Gem GST Burn", "Gem GMT Burn",
    ]
    fmt_monthly = {}
    for c in monthly.columns:
        if c != "月":
            fmt_monthly[c] = "{:,.0f}"
    st.dataframe(
        monthly.style.format(fmt_monthly),
        use_container_width=True,
    )


# ============================================================
# Tab 7: データソース
# ============================================================
with tab_sources:
    st.subheader("📚 データソース・根拠一覧")
    st.caption("全ての推定値・パラメータの根拠となるデータソースです")

    for key, info in DATA_SOURCES.items():
        with st.expander(f"📌 {info['source']}", expanded=False):
            st.markdown(f"**カテゴリ**: `{key}`")
            st.markdown(f"**URL**: [{info['url']}]({info['url']})")
            if "date" in info:
                st.markdown(f"**データ時点**: {info['date']}")
            if "value" in info:
                st.markdown(f"**値**: {info['value']}")
            if "note" in info:
                st.markdown(f"**備考**: {info['note']}")

    st.divider()
    st.subheader("⚠️ 推定値の注意事項")
    st.info("""
    **以下のパラメータは推定値です（公式データ未公開）:**

    - **2026年MAU (30,000)**: 2023年2月の42,965から減少傾向を外挿
    - **レルム別ユーザー比率**: Solana 70% / BNB 20% / Polygon 10% はDune Analyticsのトランザクション比率から推定
    - **GSTキャップ解放コスト**: Whitepaper + コミュニティ集約
    - **GMTプール分配比率**: Classic 40% / Rainbow 60% (p2e.game報道)
    - **虹靴排出確率**: Common 0.5% / Uncommon 2.5% (Whitepaper Enhancement)
    - **虹靴流通量**: stepn-market.guide リスティング数から逆算推定
    - **GMT半減後日次排出**: Dune Analytics GMT流入データから推定

    すべてのパラメータはサイドバーから自由に調整できます。
    """)

# ============================================================
# Footer
# ============================================================
st.divider()
st.caption(f"""
STEPN OG Economy Simulator v2.0 | 期間: {sim_days}日 ({sim_years:.1f}年)
| ユーザー: {total_users:,} | DAU比率: {daily_active_ratio:.0%}
| レルム: Solana({realm_params['Solana'].user_share:.0%})
/ BNB({realm_params['BNB'].user_share:.0%})
/ Polygon({realm_params['Polygon'].user_share:.0%})
| GMTプール: Classic {gmt_classic_ratio:.0%} / Rainbow {gmt_rainbow_ratio:.0%}
| 虹靴: {rb_initial_supply}足
""")
