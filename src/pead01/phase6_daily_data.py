"""Construct time-ordered signals and auditable daily trade paths."""
import numpy as np
import pandas as pd

from .__main__ import load
from .daily import DAILY_COLUMNS, prepare_daily, session_close

METHODS = ("Close→Open", "Close→Close", "Open→Close", "Open→Open")


def signal_windows(day, minutes, closes, method):
    """Use only complete pre-open or post-close release intervals."""
    if minutes < 540:
        first = day
    elif minutes > closes[day] or (minutes==closes[day] and method in METHODS[2:]):
        first = day+1
    else:
        return None
    if first <= 0 or first >= len(closes):
        return None
    return {
        METHODS[0]: (first-1, "C", first, "O"),
        METHODS[1]: (first-1, "C", first, "C"),
        METHODS[2]: (first, "O", first, "C"),
        METHODS[3]: (first, "O", first+1, "O"),
    }[method]


def make_signals(events, sessions, bars, index, closes):
    rows = []
    for e in events.itertuples(index=False):
        d = sessions.get_indexer([e.announcement_date])[0]
        if d < 0 or pd.isna(e.announcement_datetime) or e.security_code not in bars:
            continue
        time = e.announcement_datetime
        minute = time.hour*60+time.minute
        q = bars[e.security_code]
        for method in METHODS:
            window = signal_windows(d, minute, closes, method)
            if window is None:
                continue
            a, p, b, mark = window
            if b+1 >= len(sessions):
                continue
            start, finish = q[p][a], q[mark][b]
            prior = d-1
            if prior < 0 or not np.isfinite([start, finish, q["Va"][prior]]).all() or q["Va"][prior]<=0:
                continue
            if q["errors"][a] != q["errors"][b]:
                continue
            gap = finish/start-index[mark][b]/index[p][a]
            # Opening timestamps are unavailable. Freeze either observation by next morning.
            for entry in ("O","C"):
                i=b+1
                if not np.isfinite(q[entry][i]) or q["limit"][i]!=0:
                    continue
                rows.append(dict(event_id=e.event_id, code=e.security_code, sector=e.sector,
                                 release=time.tz_localize(None), method=method, entry=entry,
                                 start=i, watch_from=sessions[a]+pd.Timedelta(minutes=closes[a] if p=="C" else 540),
                                 observation_end_day=sessions[b],
                                 signal_time=sessions[b]+pd.Timedelta(minutes=closes[b]+1),
                                 order_time=sessions[i]+pd.Timedelta(minutes=539 if entry=="O" else closes[i]-10),
                                 fill_time=sessions[i]+pd.Timedelta(minutes=540 if entry=="O" else closes[i]),
                                 gap=gap, adv=q["Va"][prior], loanable=e.loanable))
    return pd.DataFrame(rows)


def paths(signals, bars, sessions, closes, hold, exit_price):
    distances=np.arange(len(sessions))
    rows=[]
    for code,g in signals.groupby("code",sort=False):
        q=bars[code]
        start=g.start.to_numpy(int)
        target=start+hold
        entry=np.where(g.entry.eq("O"),q["O"][start],q["C"][start])
        err=q["errors"][start]
        valid=np.isfinite(q[exit_price])&(q["limit"]==0)
        next_valid=np.minimum.accumulate(np.where(valid,distances,len(sessions))[::-1])[::-1]
        terminal=np.where(target<len(sessions),next_valid[target.clip(max=len(sessions)-1)],len(sessions))
        end=terminal.clip(max=len(sessions)-1)
        closed=(terminal<len(sessions))&(q["errors"][end]==err)
        end=np.where(closed,end,len(sessions)-1)
        minutes=np.where(closed,540 if exit_price=="O" else closes[end],1440)
        end_time=pd.Series(sessions.take(end)+pd.to_timedelta(minutes,unit="m"),index=g.index).where(closed)
        marks=[]
        for first,last,price,error,done in zip(start,end,entry,err,closed):
            cell=q["C"][first:last+1].copy()
            cell[q["errors"][first:last+1]!=error]=np.nan
            if done:
                cell[-1]=q[exit_price][last]
            prev=np.r_[price,cell]
            prior=np.maximum.accumulate(np.where(np.isfinite(prev),np.arange(len(prev)),0))
            marks.append(prev[prior][1:]/price)
        rows.append(g.assign(end=end,target=target,closed=closed,exit_minute=minutes,
                             label_end=end_time,marks=marks))
    return pd.concat(rows,ignore_index=True)


def load_inputs(raw, old, cfg, out):
    source=load(raw,"daily",DAILY_COLUMNS,strings=["Code"])
    cal=load(raw,"calendar",["Date","HolDiv"],strings=["HolDiv"])
    idx=load(raw,"topix",["Date","O","C"]).set_index("Date").sort_index()
    sessions=pd.DatetimeIndex(cal.loc[cal.HolDiv.isin(["1","2"]),"Date"].unique()).sort_values()
    sessions=sessions[(sessions>=source.Date.min())&(sessions<=cfg["last_session"])]
    coverage=source.groupby("Code").agg(first=("Date","min"),last=("Date","max"),rows=("Date","size"),
           traded=("Vo",lambda s:s.gt(0).sum()),no_volume=("Vo",lambda s:s.isna().sum()),
           nontraded=("Vo",lambda s:s.eq(0).sum()),adjustments=("AdjFactor",lambda s:(s.notna()&s.ne(1)).sum()))
    coverage["calendar_inside_span"]=sessions.searchsorted(coverage["last"],side="right")-sessions.searchsorted(coverage["first"])
    coverage["missing_inside_span"]=coverage.calendar_inside_span-coverage.rows
    coverage.to_parquet(out/"coverage.parquet")
    if not sessions.isin(idx.index).all() or not source.Date.isin(sessions).all():
        raise ValueError("Daily/calendar/TOPIX session mismatch")
    events=pd.read_parquet(old/"events.parquet",columns=["event_id","security_code","sector",
                           "announcement_date","announcement_datetime","attributes_date"])
    master=load(raw,"master",["Date","Code","Mrgn"],strings=["Code","Mrgn"]).set_index(["Date","Code"])
    keys=pd.MultiIndex.from_frame(events[["attributes_date","security_code"]])
    events["loanable"]=master.Mrgn.reindex(keys).eq("2").to_numpy()
    if events.attributes_date.gt(events.announcement_date).any():
        raise ValueError("Attribute chronology")
    prices=prepare_daily(source)
    del source, master
    codes=set(events.security_code)
    bars={code:dict(zip(("O","C","errors","limit","Va"),g.droplevel("Code").reindex(sessions)
          [["open","close","factor_errors","limit_flag","Va"]].to_numpy(float).T))
          for code,g in prices.groupby(level="Code",sort=False) if code in codes}
    closes=np.array([session_close(day,day in set(cal.loc[cal.HolDiv.eq("2"),"Date"])) for day in sessions])
    idx=idx.reindex(sessions)
    return events,sessions,bars,idx,closes
