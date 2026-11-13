# Phase 1A データ取得可能性

2026年11月13日 JST の既存 CLI 認証で確認した。財務APIは契約開始日の下限として2021年11月13日を返し、2016年の要求は HTTP 400。TOPIX、日足・銘柄マスタのバルク、株式分足が利用可能。TDnet インデックスは HTTP 403。追加の購入は行っていない。

| 必要データ | API・実際の取得範囲と制約 |
| --- | --- |
| 実績開示日・時刻、決算期、実績と会社予想 | `/v2/fins/summary`、バルクは月または日。TDnetの開示日・分時刻、開示番号、連結区分と会計基準を収録。予定発表日のAPIは実績時刻の根拠に使わない。財務速報・確報はTDnet公表から遅れ、J-Quants側の行単位利用可能時刻は非提供。 |
| 会社予想修正 | 同じ財務サマリー内の短信および業績予想修正。比較対象年度と開示順を照合。訂正は別番号で残るが訂正識別フラグがなく、配信不備の上書き前データは取得できない。 |
| 日足・調整係数 | `/v2/equities/bars/daily`、契約範囲の全銘柄。バルクは調整前と権利落ち日の係数。取引のない行は価格や出来高が欠損し得る。 |
| 分足 | `/v2/equities/bars/minute`、契約上は直近2年。今回は2026年8〜10月の全銘柄バルク。東証立会内の約定を集約し、無約定分は配信されない。時刻は各分の開始で JST。 |
| 銘柄属性と時価総額 | `/v2/equities/master` の日付付きコード・会社名・市場・33業種・商品区分。日足の `MktCap` は百万円単位の指数用上場株式数ベース時価総額。別の算式を使用する valuation API は混合していない。 |
| TOPIX | `/v2/indices/bars/daily/topix` の四本値、配当なし。J-Quantsの分足アドオンには指数分足がない。休日判定は `/v2/markets/calendar`。 |
| 市場コンセンサス・保有主体別比率 | 履歴を取得できる既存契約ソースは確認できなかった。EDINETや発行体の有報は保有属性の代替候補だが、公開日時・対象期を付けた横断データは未整備。投資部門別売買状況は銘柄別の保有比率と定義が異なる。 |

出典は [契約別仕様](https://jpx-jquants.com/ja/spec/data-spec)、[財務サマリー](https://jpx-jquants.com/en/spec/fin-summary)、[株価日足](https://jpx-jquants.com/en/spec/eq-bars-daily)、[株価分足](https://jpx-jquants.com/ja/spec/eq-bars-minute)、[バリュエーション](https://jpx-jquants.com/en/spec/eq-valuation)、[データ修正履歴](https://jpx-jquants.com/en/spec/fix-data-info)、[取引カレンダー](https://jpx-jquants.com/en/spec/mkt-cal)。

公表月額は Free 0円、Light 1,650円、Standard 3,300円、Premium 16,500円。株式分足・ティックは5,500円、TDnetは11,000円の追加月額。基本プランのレート上限は順に5・60・120・500件/分、分足60件/分、TDnet100件/分。財務サマリーには独自の上限がある。取得は月次バルクを優先し、HTTP 429時は待機して再試行する。[料金表](https://jpx-jquants.com/apidoc.html) · [レート制限](https://jpx-jquants.com/ja/spec/rate-limits)

JPXの公開TDnetは31日間、東証上場会社情報サービスは銘柄別に過去10年の資料を閲覧できる。旧年の開示原文・訂正の照合候補になる。公開サイトからの上場廃止銘柄込みの全件一括取得経路と、対応する日足の再現可能な組み合わせは確立していない。発行体IRは銘柄別補助、EDINETは法定開示の時刻であり、短信発表時刻としては扱えない。有料TDnet APIは5年、DataCubeは保存期間外データの購入候補。2016〜2021年11月12日は本集計に入れていない。[TDnet概要](https://www.jpx.co.jp/equities/listing/disclosure/tdnet/index.html) · [TDnet API](https://www.jpx.co.jp/markets/paid-info-listing/tdnet/) · [J-Quants FAQ](https://jpx-jquants.com/ja/help/about)
