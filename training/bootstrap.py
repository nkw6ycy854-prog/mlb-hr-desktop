from __future__ import annotations

from datetime import date,timedelta
from pathlib import Path

from mlb_hr.providers.statcast import StatcastProvider
from mlb_hr.storage.analytics import AnalyticsStore


def bootstrap_statcast(parquet_dir:Path,start:date,end:date)->dict[str,int]:
    store=AnalyticsStore(parquet_dir);provider=StatcastProvider();stats={"downloaded":0,"skipped":0,"failed":0,"empty":0}
    d=start
    while d<=end:
        final=parquet_dir/f"season={d.year}"/f"month={d.month:02d}"/f"statcast_{d.isoformat()}.parquet"
        if final.exists() and final.stat().st_size>0:
            stats["skipped"]+=1;d+=timedelta(days=1);continue
        res=provider.fetch_day(d)
        if not res.ok:
            stats["failed"]+=1;d+=timedelta(days=1);continue
        if not res.data:
            stats["empty"]+=1;d+=timedelta(days=1);continue
        store.write_statcast_day(res.data,d);stats["downloaded"]+=1;d+=timedelta(days=1)
    store.close();return stats
