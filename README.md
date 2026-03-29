# STEPN OG Economy Simulator

STEPN (Move-to-Earn) の OG トークノミクスシミュレーター。全3レルム（Solana / BNB Chain / Polygon）対応、最大4年間の経済動態を可視化します。

## 機能

- **GST経済**: Mint/Burn バランス、供給量推移、インフレ率
- **GMT・虹靴**: クラシック/レインボープール分配、半減期、虹靴ライフサイクル
- **ユーザーセグメント**: 12セグメント (1R/2E カジュアル〜3R/60E MAX)
- **スニーカー経済**: レアリティ別 (Common〜Legendary) 供給推移
- **ミステリーボックス**: MB開封、ジェム・Mint Scroll ドロップ
- **ジェム経済**: Lv1〜Lv9 アップグレードチェーン、GST/GMT バーン
- **全パラメータ調整可能**: サイドバーからリアルタイム変更

## データソース

- [STEPN Whitepaper](https://whitepaper.stepn.com/)
- [CoinGecko GST/GMT](https://www.coingecko.com/en/coins/green-satoshi-token)
- [Dune Analytics](https://dune.com/nguyentoan/STEPN-(GMT,-GST)-Core-Metrics)
- [STEPN-MARKET.GUIDE](https://stepn-market.guide/)

## ローカル実行

```bash
pip install -r requirements.txt
streamlit run stepn_app.py
```

## ファイル構成

| ファイル | 内容 |
|---------|------|
| `stepn_engine.py` | シミュレーションエンジン (全定数・ロジック) |
| `stepn_app.py` | Streamlit ダッシュボード UI |
| `requirements.txt` | Python依存パッケージ |
