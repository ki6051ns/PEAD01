import numpy as np
import pandas as pd

from pead01.phase7_statistics import adoption_metrics, event_metrics, periodic_metrics
from pead01.phase7_statistics_report import composition


def test_periodic_compounding_matches_daily_nav_across_calendar_boundaries():
    dates=pd.DatetimeIndex(["2024-12-30","2025-01-06","2025-02-03","2025-04-01"])
    frame=pd.DataFrame(dict(mode="single_w252_b10",date=dates,net=[.10,-.10,.03,-.02],
                           fills=[1,0,1,0],utilization=.2,turnover=.1,cost=.001,
                           long_gross=.02,short_gross=0.))
    market=pd.Series([.02,.01,-.02,.03],index=dates)
    answer=periodic_metrics(frame,market)
    for grain in ("month","quarter","year"):
        sample=answer.loc[answer.level.eq(grain)]
        assert sample.days.sum()==len(frame)
        np.testing.assert_allclose((1+sample.cumulative).prod(),(1+frame.net).prod())
    assert answer.loc[answer.level.eq("quarter")].period.tolist()==["2024Q4","2025Q1","2025Q2"]


def test_same_event_is_aggregated_across_positions_and_losses_are_not_ranked():
    dates=pd.DatetimeIndex(["2025-04-01","2025-04-02"])
    journal=pd.DataFrame(dict(date=[dates[0],dates[1],dates[0],dates[1]],event=["a","a","b","c"],
                             net=[.02,.03,.01,-.04],net_capital=[.02,.0309,.01,-.0412],side=[1,1,1,-1]))
    net=pd.Series([.03,-.01],index=dates)
    sample=event_metrics(journal,net).query("level=='full'").iloc[0]
    assert sample.events==3 and sample.positive_events==2
    np.testing.assert_allclose(sample.positive_share_top1,.0509/.0609)
    np.testing.assert_allclose(sample.period_return_without_top10,-.04)


def test_adoption_and_realized_contribution_are_distinct_and_cash_is_implicit():
    catalogue=pd.DataFrame({"id":[0,1],"method":["A","B"],"hold":[1,2]})
    selection=pd.DataFrame({"mode":["m","m"],"id":[0,1],"weight":[.25,.75],"start":[0,0],"end":[3,3]})
    realized=pd.DataFrame(dict(mode=["m"],axis=["method"],bucket=["A"],fills=[1],capital_contribution=[.02]))
    result=composition(realized,adoption_metrics(selection,catalogue),["m","cash"],catalogue,4)
    within=result.query("axis=='method'").set_index(["mode","bucket"])
    np.testing.assert_allclose(within.loc["m"].adoption_share.sum(),.75)
    assert within.loc[("m","B"),"fills"]==0
    assert within.loc["cash"].adoption_share.sum()==0
