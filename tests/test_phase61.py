from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from pead01.phase61 import simulate, pareto


def order(code="72030", side=1, size=.01, marks=(1., 1.02)):
    row = SimpleNamespace(start=0, end=1, minute=540, exit_minute=930, code=code, cost=20,
                          hedge=False, beta=np.nan, capacity=size, closed=True, marks=marks)
    return ((row, side, 1.), "single")


def execute(orders, rates, restrictions=None, multiple=1, leverage=3):
    days = pd.DatetimeIndex(["2026-01-09", "2026-01-13"])
    policy = [(multiple, leverage, 1., {"single": 1.})]*2
    return simulate(orders, days, policy, rates, restrictions or {}, np.zeros((2,2)))


def test_financing_weekend_nav_and_adv_cap():
    d = execute([order()], (False,.0365,0.,1.), multiple=10)
    assert d.peak_yen.iloc[0] == 1_000_000
    assert d.funding.iloc[1] == pytest.approx(400)
    assert d.nav.iloc[-1] == pytest.approx(100_000_000+20_000-1_000-1_020-400)


def test_global_leverage_restrictions_and_cash_short():
    entries = [order(str(i),size=.10,marks=(1.,1.)) for i in range(30)]
    result = execute(entries,(False,0.,0.,1.),multiple=10,leverage=1.5)
    assert result.peak_yen.iloc[0] <= 150e6
    restricted = execute([order()],(False,0.,0.,1.),{pd.Timestamp("2026-01-09"):{"72030":1.}})
    assert restricted.fills.sum() == 0
    assert execute([order(side=-1)],(True,0.,0.,1.)).fills.sum() == 0


def test_same_code_opposing_sleeves_net():
    result = execute([order(),order(side=-1)],(False,0.,0.,1.))
    assert result.fills.sum() == 0


def test_pareto_treats_smaller_drawdown_as_better():
    data = pd.DataFrame([[1,.03,-.02,.1],[1,.03,-.03,.1],[1.2,.02,-.02,.1]],
                        columns=["sharpe","annual","max_dd","utilization"])
    assert pareto(data) == [True, False, True]
