"""Read-only chronological weather-model experiment, with local artifacts only.

Run: python -m scripts.evaluate_weather_prediction
This does not change production thresholds, activate models or write predictions.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from prediction.config import PredictionOptions
from prediction.data import load_history, training_examples
from prediction.learning import fit_forest, infer, scores, split_by_time
from shared.config import Settings
from shared.database import make_engine
from shared.time import utcnow


def main():
    settings, options = Settings.load(outbound=False), PredictionOptions.load()
    cutoff = utcnow()
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            if engine.dialect.name == 'mysql':
                connection.exec_driver_sql('SET SESSION TRANSACTION READ ONLY')
            with Session(bind=connection) as session:
                stations, groups = load_history(session, settings, cutoff, options)
                rows, excluded = training_examples(stations, groups, settings, options)
                raw_count = sum(len(g) for g in groups.values())
    finally:
        engine.dispose()
    complete = [r for r in rows if r['features'] is not None and r['features']['weather'] is not None]
    train, validation, test, split = split_by_time(complete)
    days = sorted({r['input_time'].astimezone(ZoneInfo('America/New_York')).date().isoformat() for r in complete})
    counts = Counter(r['station_id'] for r in complete)
    reasons = []
    if len(days) < options.min_training_days:
        reasons.append('too_few_local_days')
    if len(complete) < options.min_training_samples:
        reasons.append('too_few_complete_samples')
    if not stations or any(counts[s.station_id] < options.min_station_samples for s in stations):
        reasons.append('too_few_samples_for_monitored_station')
    if min(len(train),len(validation),len(test)) < options.min_holdout_samples:
        reasons.append('too_small_temporal_split')
    if {r['station_id'] for r in complete} - {r['station_id'] for r in train}:
        reasons.append('holdout_station_missing_from_train')
    report = {'database_written':False, 'model_activated':False, 'source':settings.bike_source,
        'cutoff':cutoff.isoformat(), 'configuration':options.as_dict(),
        'production_readiness_reasons':reasons, 'status':'insufficient_data',
        'observations':raw_count, 'baseline_examples':len(rows), 'complete_weather_examples':len(complete),
        'missing_lag_features':sum(r['features'] is None for r in rows),
        'missing_weather_features':sum(r['features'] is not None and r['features']['weather'] is None for r in rows),
        'excluded':excluded,'local_days':len(days),'local_dates':days,'split':split,
        'stations':[{'station_id':s.station_id,'name':s.name,'samples':counts[s.station_id]} for s in stations],
        'policy':'Actual observations and labels only; chronological holdouts; boundary labels purged; weather known at issue time.',
        'dataset_hash':hashlib.sha256(json.dumps([
            [r['input_observation_id'],r['actual_observation_id']] for r in complete]).encode()).hexdigest(),
        'candidates':[], 'models':{}}
    target = Path('artifacts/prediction_weather') / cutoff.strftime('%Y%m%dT%H%M%SZ')
    target.mkdir(parents=True,exist_ok=True)
    # A local experiment can run with >=7 real days; production still requires its configured minimum.
    can_fit = len(days)>=7 and not any(r!='too_few_local_days' for r in reasons)
    if can_fit:
        report['status']='experimental' if reasons else 'evaluated'
        report['baseline']={name:scores(part,[r['baseline'] for r in part])
            for name,part in (('validation',validation),('test',test))}
        for with_weather in (False,True):
            candidates=[]
            for depth in (4,8):
                artifact=fit_forest(train,with_weather=with_weather,depth=depth)
                metrics=scores(validation,[infer(artifact,r['features'],r['station_id']) for r in validation])
                report['candidates'].append({'with_weather':with_weather,'depth':depth,'validation':metrics})
                candidates.append((metrics['mae'],depth,artifact,metrics))
            _,depth,artifact,metrics=min(candidates,key=lambda c:(c[0],c[1]))
            name='with_weather' if with_weather else 'without_weather'
            report['models'][name]={'depth':depth,'validation':metrics,
                'test':scores(test,[infer(artifact,r['features'],r['station_id']) for r in test])}
            (target/(name+'.json')).write_text(json.dumps(artifact),encoding='utf-8')
    (target/'report.json').write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    lines=['# Đánh giá dự đoán số xe sau 30 phút','',
        f"Dữ liệu thật: {raw_count} quan sát; {len(complete)} mẫu đủ biến xe và thời tiết; {len(days)} ngày.",
        f"Trạng thái: {report['status']}. Không ghi DB hoặc kích hoạt mô hình.",
        f"Điều kiện sản xuất còn thiếu: {', '.join(reasons) or 'Không thiếu điều kiện dữ liệu'}.",'',
        'Tách theo thời gian; chọn độ sâu bằng tập xác thực; chấm sai số trên tập kiểm thử riêng.',
        'Các mô hình lưu tại đây chỉ huấn luyện trên tập train, phục vụ tái lập đánh giá.','',
        '| Mô hình | MAE kiểm thử (xe) | RMSE kiểm thử (xe) | Số mẫu |',
        '|---|---:|---:|---:|']
    if can_fit:
        for label,metrics in [('Cơ sở',report['baseline']['test']),
            ('Rừng ngẫu nhiên không thời tiết',report['models']['without_weather']['test']),
            ('Rừng ngẫu nhiên có thời tiết',report['models']['with_weather']['test'])]:
            lines.append(f"| {label} | {metrics['mae']:.3f} | {metrics['rmse']:.3f} | {metrics['sample_count']} |")
        lines.extend(['', '## Sai số MAE theo trạm (xe)', '',
            '| Trạm | Cơ sở | Không thời tiết | Có thời tiết |', '|---|---:|---:|---:|'])
        for station in stations:
            sid=station.station_id
            metrics=[report['baseline']['test']['per_station'].get(sid),
                report['models']['without_weather']['test']['per_station'].get(sid),
                report['models']['with_weather']['test']['per_station'].get(sid)]
            values=['—' if m is None else f"{m['mae']:.3f}" for m in metrics]
            lines.append('| '+station.name+' | '+' | '.join(values)+' |')
    (target/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target/'report.md'),'status':report['status'],
        'local_days':len(days),'complete_weather_examples':len(complete),'split':split,
        'production_readiness_reasons':reasons,
        'test_scores':{name:{k:m['test'][k] for k in ('mae','rmse','sample_count')}
            for name,m in ({'baseline':report['baseline'],**report['models']}.items() if can_fit else [])}},default=str))


if __name__=='__main__':
    main()
