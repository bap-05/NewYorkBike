"""Normalize station Parquets, cache historical weather, evaluate +30m models offline."""
import argparse
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ingestion.clients.http import get_json, SourceError
from ingestion.clients.proxy import OutboundClient
from prediction.historical_dataset import normalize_bikes, join_historical_weather, historical_examples, learning_rows
from prediction.learning import fit_forest, infer, scores, split_by_time
from shared.config import Settings
from shared.database import make_engine
from shared.models import Station
from shared.time import utcnow

ENDPOINT='https://archive-api.open-meteo.com/v1/archive'
VARIABLES={'temperature_2m':'temperature','relative_humidity_2m':'humidity','rain':'rain','wind_speed_10m':'wind_speed'}


def fetch_weather(settings,stations,start,end,cache):
    frames=[]
    cache.mkdir(parents=True,exist_ok=True)
    with OutboundClient(settings) as client:
        for station in stations:
            params={'latitude':str(station['latitude']),'longitude':str(station['longitude']),
                'start_date':(start-pd.Timedelta(days=1)).date().isoformat(),
                'end_date':(end-pd.Timedelta(seconds=1)).date().isoformat(),
                'hourly':','.join(VARIABLES),'timezone':'UTC','timeformat':'unixtime',
                'temperature_unit':'celsius','wind_speed_unit':'ms','precipitation_unit':'mm','models':'era5'}
            key=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()[:20]
            path=cache/(station['station_id']+'-'+key+'.json')
            if path.is_file():
                saved=json.loads(path.read_text(encoding='utf-8'))
                if saved['request']!=params:
                    raise ValueError('Cached weather request mismatch')
            else:
                payload=get_json(client,ENDPOINT,source='open-meteo-archive',params=params,
                    attempts=settings.max_attempts,backoff=settings.backoff_seconds)
                saved={'endpoint':ENDPOINT,'request':params,'retrieved_at':utcnow().isoformat(),'payload':payload}
                path.write_text(json.dumps(saved,ensure_ascii=True)+'\n',encoding='utf-8')
            payload=saved['payload']
            expected={'temperature_2m':'\u00b0C','relative_humidity_2m':'%','rain':'mm','wind_speed_10m':'m/s'}
            if any(payload.get('hourly_units',{}).get(k)!=v for k,v in expected.items()):
                raise ValueError('Unexpected historical weather units')
            frame=pd.DataFrame(payload['hourly']).rename(columns=VARIABLES)
            frame['weather_time']=pd.to_datetime(frame.pop('time'),unit='s',utc=True)
            frame['station_id']=station['station_id']
            frame['weather_retrieved_at']=saved['retrieved_at']
            frame['weather_source']='open-meteo-era5-reanalysis'
            frame['weather_cache_file']=path.name
            if frame.weather_time.duplicated().any():
                raise ValueError('Duplicate hourly weather timestamps')
            frames.append(frame)
            print('Weather ready: '+station['station_id']+' hours='+str(len(frame)),flush=True)
    return pd.concat(frames,ignore_index=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',required=True)
    parser.add_argument('--start-date',default='2026-10-01')
    parser.add_argument('--end-date',default='2026-10-31',help='Inclusive UTC date')
    parser.add_argument('--output-dir',default='artifacts/historical_prediction')
    args=parser.parse_args()
    settings=Settings.load()
    start=pd.Timestamp(args.start_date,tz='UTC'); end=pd.Timestamp(args.end_date,tz='UTC')+pd.Timedelta(days=1)
    if end<=start or end>pd.Timestamp(utcnow()):
        raise ValueError('A completed historical date range is required')
    root=Path(args.output_dir);root.mkdir(parents=True,exist_ok=True)
    output=root/utcnow().strftime('%Y%m%dT%H%M%SZ');output.mkdir()
    engine=make_engine(settings)
    try:
        with Session(engine) as session:
            stations=[{'station_id':s.station_id,'name':s.name,'latitude':str(s.latitude),'longitude':str(s.longitude)}
                for s in session.scalars(select(Station).where(Station.source=='citibike',Station.is_monitored.is_(True)).order_by(Station.station_id))]
    finally:
        engine.dispose()
    known={s['station_id'] for s in stations}
    files=sorted(Path(args.input_dir).glob('*.parquet'))
    if not files:
        raise ValueError('No Parquet files found')
    manifest=[{'file':str(p.resolve()),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    raw=pd.concat([pd.read_parquet(p) for p in files],ignore_index=True)
    bikes,audit=normalize_bikes(raw,start=start,end=end,known_ids=known)
    if set(bikes.station_id)!=known:
        raise ValueError('Historical data must cover every monitored station')
    bikes.loc[bikes.valid].to_parquet(output/'clean_bikes.parquet',index=False)
    bikes.loc[~bikes.valid].to_parquet(output/'rejected_bike_slots.parquet',index=False)
    print('Normalized bikes: '+json.dumps(audit),flush=True)
    weather=fetch_weather(settings,stations,start,end,root/'weather_cache')
    weather.to_parquet(output/'weather_hourly.parquet',index=False)
    joined=join_historical_weather(bikes,weather)
    joined.loc[joined.valid].to_parquet(output/'bikes_with_weather.parquet',index=False)
    examples=historical_examples(joined)
    examples.to_parquet(output/'training_examples.parquet',index=False)
    rows=learning_rows(examples)
    train,val,test,split=split_by_time(rows)
    if min(len(train),len(val),len(test))<50:
        raise ValueError('Insufficient chronological holdout samples')
    print('Training/evaluation split: '+json.dumps(split),flush=True)
    report={'database_written':False,'model_activated':False,'historical_range_utc':[start.isoformat(),end.isoformat()],
        'created_at':utcnow().isoformat(),'inputs':manifest,'stations':stations,'audit':audit,
        'complete_examples':len(rows),'excluded_missing_weather':len(examples)-len(rows),
        'local_days':len({r['input_time'].astimezone(ZoneInfo('America/New_York')).date() for r in rows}),
        'split':split,'timestamp_tolerance_seconds':120,'sampling_seconds':300,
        'weather_policy':{'source':'Open-Meteo ERA5 reanalysis','documentation':'https://open-meteo.com/en/docs/historical-weather-api',
            'join':'backward hourly, age <=3600s, no future interpolation','retrieved_at':'recorded separately in cached payloads',
            'limitation':'Retrospective reanalysis; not proof of weather information available at historical issue time. Offline evaluation only.',
            'rain':'preceding-hour sum, mm; different interval from live current rain'},
        'baseline':{name:scores(part,[r['baseline'] for r in part]) for name,part in (('validation',val),('test',test))},
        'models':{},'candidates':[]}
    for with_weather in (False,True):
        candidates=[]
        for depth in (4,8,12):
            print(f'Fitting Random Forest: weather={with_weather} depth={depth}',flush=True)
            artifact=fit_forest(train,with_weather=with_weather,depth=depth)
            metric=scores(val,[infer(artifact,r['features'],r['station_id']) for r in val])
            report['candidates'].append({'with_weather':with_weather,'depth':depth,'validation':metric})
            candidates.append((metric['mae'],depth,artifact,metric))
        _,depth,artifact,metric=min(candidates,key=lambda row:(row[0],row[1]))
        name='with_weather' if with_weather else 'without_weather'
        report['models'][name]={'depth':depth,'validation':metric,
            'test':scores(test,[infer(artifact,r['features'],r['station_id']) for r in test])}
        artifact['offline_historical_policy']=report['weather_policy']
        (output/(name+'.json')).write_text(json.dumps(artifact)+'\n',encoding='utf-8')
    report['selected_by_validation']=min(['baseline',*report['models']],key=lambda name:
        (report['baseline'] if name=='baseline' else report['models'][name])['validation']['mae'])
    (output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    write_report(output,report)
    print(json.dumps({'report':str(output/'report.md'),'complete_examples':len(rows),'local_days':report['local_days'],
        'selected_by_validation':report['selected_by_validation'],'test_scores':{name:{k:model['test'][k]
            for k in ('mae','rmse','sample_count')} for name,model in {'baseline':report['baseline'],**report['models']}.items()}}),flush=True)


def write_report(output,report):
    labels={'baseline':'Cơ sở: giữ nguyên số xe','without_weather':'Random Forest không thời tiết','with_weather':'Random Forest có thời tiết'}
    models={'baseline':report['baseline'],**report['models']}
    lines=['# Huấn luyện dự đoán +30 phút từ dữ liệu lịch sử tháng 10','',
        f"Dữ liệu đầu vào: {report['audit']['rows_in_range']:,} dòng; {report['complete_examples']:,} cặp mẫu đầy đủ.",
        f"Phân chia theo thời gian: {json.dumps(report['split'],ensure_ascii=False)}.",'',
        'Chọn độ sâu theo MAE xác thực; tập kiểm thử không dùng để chọn mô hình. Loại nhãn vượt ranh giới tập.',
        'Thời tiết: [Open-Meteo ERA5](https://open-meteo.com/en/docs/historical-weather-api). Ghép giờ trước gần nhất; không nội suy từ giờ tương lai.',
        'ERA5 là tái phân tích hồi cứu. Kết quả này không chứng minh hiệu quả phục vụ trực tiếp với thời tiết realtime.',
        'Không ghi vào DB quan sát thật, không kích hoạt mô hình. Dữ liệu gốc và thời điểm tải được giữ trong manifest/cache.','',
        '| Mô hình | MAE xác thực | MAE kiểm thử (xe) | RMSE kiểm thử (xe) | Số mẫu kiểm thử |',
        '|---|---:|---:|---:|---:|']
    for name,m in models.items():
        lines.append(f"| {labels[name]} | {m['validation']['mae']:.3f} | {m['test']['mae']:.3f} | {m['test']['rmse']:.3f} | {m['test']['sample_count']} |")
    lines.extend(['',f"Lựa chọn theo tập xác thực: **{labels[report['selected_by_validation']]}**.",'',
        '## MAE kiểm thử theo trạm','', '| Trạm | Cơ sở | ML không thời tiết | ML có thời tiết |','|---|---:|---:|---:|'])
    for s in report['stations']:
        metrics=[m['test']['per_station'].get(s['station_id']) for m in models.values()]
        values=['—' if m is None else f"{m['mae']:.3f}" for m in metrics]
        lines.append('| '+s['name']+' | '+' | '.join(values)+' |')
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    try:
        main()
    except SourceError as exc:
        raise SystemExit(str(exc)) from None
