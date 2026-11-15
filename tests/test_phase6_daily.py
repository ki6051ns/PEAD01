import numpy as np
import pandas as pd

from pead01.phase6_daily_data import METHODS, make_signals, paths, signal_windows
from pead01.phase6_daily_wf import eligible, fold_windows, observations, replay
from pead01.phase6_validation_daily import block_max_test


def test_close_minute_is_ambiguous_and_intraday_is_excluded():
    closes=[900,900,930,930]
    assert signal_windows(1,900,closes,METHODS[0]) is None
    assert signal_windows(1,900,closes,METHODS[2])==(2,"O",2,"C")
    assert all(signal_windows(2,800,closes,m) is None for m in METHODS)
    assert signal_windows(2,931,closes,METHODS[1])==(2,"C",3,"C")


def test_purge_uses_actual_end_and_applies_blank_at_both_boundaries():
    start=np.array([2,2,2,0,3])
    signal=np.array([1,1,1,0,0])
    end=np.array([3,5,7,2,4])
    assert eligible(start,signal,end,1,5).tolist()==[True,False,False,False,False]
    assert fold_windows(300,126,10,45)==((109,235),(245,290))


def test_signal_and_delayed_close_and_costs():
    days=pd.bdate_range("2025-01-06",periods=8)
    closes=np.full(len(days),930)
    open_=np.array([100,110,111,112,113,114,115,116],dtype=float)
    close=np.array([100,111,112,np.nan,114,115,116,117],dtype=float)
    events=pd.DataFrame({"event_id":["e"],"security_code":["x"],"sector":["s"],"loanable":[True],
                         "announcement_date":[days[0]+pd.Timedelta(days=1)],
                         "announcement_datetime":[(days[1]+pd.Timedelta(hours=8)).tz_localize("Asia/Tokyo")]})
    bars={"x":{"O":open_,"C":close,"errors":np.zeros(8),"limit":np.zeros(8),"Va":np.repeat(1e9,8)}}
    market=pd.DataFrame({"O":100.,"C":100.},index=days)
    signals=make_signals(events,days,bars,market,closes)
    assert (signals.signal_time<signals.order_time).all()
    assert (signals.order_time<signals.fill_time).all()
    selected=signals.loc[signals.method.eq(METHODS[0])&signals.entry.eq("O")]
    t=paths(selected,bars,days,closes,1,"C").assign(hold=1,exit_price="C")
    assert t.target.iloc[0]==3 and t.end.iloc[0]==4
    assert t.label_end.iloc[0]==days[4]+pd.Timedelta(minutes=930)
    cfg={"directions":["long"],"thresholds":[0],"position_limit":1e6,
         "capital":1e8,"participation":.01,"cost_bp":20}
    c,_,audit=observations(t,cfg,days,[(0,4),(0,5)])
    assert audit.fills.tolist()==[0,1] and audit.purged.tolist()==[1,0]
    history=pd.DataFrame({"id":[0],"start":[0],"end":[8],"mode":["single"],"weight":[1.]})
    out=replay(t,c,history,days,cfg,contributions=True)
    assert out.fills.sum()==1
    assert out.cost.sum()>0
    np.testing.assert_allclose(out.long_gross+out.short_gross,out.gross)
    repeated=pd.concat([history,history.assign(mode="blank",weight=.3),
                        history.assign(mode="blank",weight=.7)],ignore_index=True)
    split=replay(t,c,repeated,days,cfg,contributions=True)
    np.testing.assert_allclose(split.loc[split["mode"].eq("single"),"net"],
                               split.loc[split["mode"].eq("blank"),"net"])


def test_end_of_snapshot_remains_unrealized():
    days=pd.bdate_range("2025-01-06",periods=3)
    signals=pd.DataFrame({"code":["x"],"entry":["O"],"start":[1]})
    price=np.array([100.,101.,102.])
    bars={"x":{"O":price,"C":price,"errors":np.zeros(3),"limit":np.zeros(3)}}
    result=paths(signals,bars,days,np.repeat(930,3),2,"C").iloc[0]
    assert not result.closed and pd.isna(result.label_end)
    assert result.end==2
    np.testing.assert_allclose(result.marks,[1,102/101])


def test_block_max_is_reproducible_and_ignores_cash_columns():
    matrix=np.column_stack((np.arange(15)*.001,np.zeros(15)))
    result=block_max_test(matrix,3,draws=49)
    np.testing.assert_array_equal(result,block_max_test(matrix,3,draws=49))
    assert 0<result[0]<=1 and np.isnan(result[1])
