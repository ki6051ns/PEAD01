import numpy as np
import pandas as pd

from pead01.phase3_portfolio import performance
from pead01.phase7 import linked_journal, turnover, validate_journal, window_scores, windows


def test_windows_keep_full_lengths_and_include_final_rolling_start():
    periods=list(windows(516))
    assert [s for kind,n,s in periods if kind=="nonoverlap" and n==126]==[0,126,252,378]
    assert [s for kind,n,s in periods if kind=="rolling" and n==504]==[0,5,10,12]
    assert all(s>=0 and s+n<=516 for _,n,s in periods)
    assert list(windows(125))==[]


def test_turnover_combines_duplicate_sleeves_and_tracks_cash():
    selection=pd.DataFrame([
        ("m",0,1,.4),("m",0,1,.1),("m",0,2,.5),
        ("m",1,1,.75),("m",1,3,.25),("m",2,-1,0.)
    ],columns=["mode","start","id","weight"])
    results=turnover(selection)
    np.testing.assert_allclose(results.retained,[.5,0])
    np.testing.assert_allclose(results.jaccard,[1/3,0])
    np.testing.assert_allclose(results.weight_change,[.5,1.])


def test_linked_pnl_matches_compounded_return():
    dates=pd.bdate_range("2025-01-01",periods=2)
    a=pd.DataFrame({"date":[dates[0],dates[0],dates[1]],"gross":[.06,.06,-.07],"cost":[.01,.01,.03]})
    r=pd.Series([.1,-.1],index=dates)
    validate_journal(a,r)
    np.testing.assert_allclose(linked_journal(a,r).net_capital.sum(),(1+r).prod()-1)


def test_window_stats_match_frozen_portfolio_definitions():
    dates=pd.bdate_range("2025-01-01",periods=126)
    daily=pd.DataFrame({"risk":np.linspace(-.004,.003,126),"cash":0.},index=dates)
    first=window_scores(daily).query("kind=='nonoverlap'").set_index("mode")
    expected=performance(daily.risk)
    for key in ("sharpe","annual","max_dd"):
        np.testing.assert_allclose(first.loc["risk",key],expected[key])
    assert np.isnan(first.loc["cash","sharpe"])
