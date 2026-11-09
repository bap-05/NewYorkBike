from datetime import timedelta
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Query

from backend.app.dependencies import ReadContext, get_context
from shared.time import as_utc

Context=Annotated[ReadContext,Depends(get_context)]
Source=Literal['citibike','seoul']
Limit=Annotated[int,Query(ge=1,le=500)]
Offset=Annotated[int,Query(ge=0,le=100000)]
StationId=Annotated[str,Query(min_length=1,max_length=128)]
ConfigHash=Annotated[str|None,Query(pattern=r'^[0-9a-f]{64}$')]


def date_range(ctx,start,end,default_days=1):
    end=as_utc(end) if end is not None else ctx.now
    start=as_utc(start) if start is not None else end-timedelta(days=default_days)
    if start>=end or (end-start).total_seconds()>ctx.options.max_range_days*86400 or end>ctx.now:
        raise HTTPException(422,detail=f'Use from < to <= now, with a range of at most {ctx.options.max_range_days} days and explicit UTC offsets.')
    return start,end
