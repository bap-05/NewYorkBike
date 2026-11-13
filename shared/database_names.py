"""Vietnamese physical SQL names, with stable Python/API attribute keys."""
import os
import re

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import mapped_column

# Migration 0007 uses Vietnamese physical names; English mode targets compatibility views.
DEFAULT_LANGUAGE = 'vietnamese'
LANGUAGE = os.getenv('DATABASE_SCHEMA_LANGUAGE', DEFAULT_LANGUAGE)
if LANGUAGE not in ('english','vietnamese'):
    raise ValueError('DATABASE_SCHEMA_LANGUAGE must be english or vietnamese')

TABLE_NAMES = {
    'stations':'tram_xe','collection_runs':'luot_thu_thap','bike_observations':'lich_su_so_xe',
    'weather_observations':'lich_su_thoi_tiet','observation_weather_links':'lien_ket_xe_thoi_tiet',
    'service_runs':'luot_chay_dich_vu','analysis_results':'ket_qua_phan_tich',
    'clustering_runs':'luot_phan_cum','station_clusters':'nhom_tram',
    'model_versions':'phien_ban_mo_hinh','training_jobs':'luot_huan_luyen','predictions':'du_doan_so_xe',
}
COLUMN_NAMES = {
    'id':'ma','source':'nguon','station_id':'ma_tram','name':'ten','latitude':'vi_do','longitude':'kinh_do',
    'rack_count':'so_gia_xe','capacity':'suc_chua','information_updated_at':'thoi_diem_cap_nhat_thong_tin',
    'is_monitored':'dang_theo_doi','updated_at':'cap_nhat_luc','scheduled_at':'thoi_diem_lich',
    'started_at':'bat_dau_luc','finished_at':'ket_thuc_luc','feed_metadata':'thong_tin_nguon',
    'bronze_manifest_path':'duong_dan_manifest_bronze','status':'trang_thai',
    'success_count':'so_thanh_cong','error_count':'so_loi','attempt_count':'so_lan_thu','error_summary':'tom_tat_loi',
    'collection_run_id':'ma_luot_thu_thap','sampled_at':'thoi_diem_mau','collected_at':'thoi_diem_thu_thap',
    'source_observed_at':'thoi_diem_nguon','available_bikes':'so_xe_co_the_thue','available_docks':'so_cho_tra_xe',
    'is_installed':'da_lap_dat','is_renting':'cho_phep_thue','is_returning':'cho_phep_tra',
    'feed_last_updated':'thoi_diem_cap_nhat_nguon','gbfs_version':'phien_ban_gbfs','quality_status':'chat_luong_du_lieu',
    'requested_latitude':'vi_do_yeu_cau','requested_longitude':'kinh_do_yeu_cau',
    'returned_latitude':'vi_do_tra_ve','returned_longitude':'kinh_do_tra_ve','weather_time':'thoi_diem_thoi_tiet',
    'temperature':'nhiet_do','humidity':'do_am','rain':'luong_mua','wind_speed':'toc_do_gio','units':'don_vi',
    'temperature_unit':'don_vi_nhiet_do','humidity_unit':'don_vi_do_am','rain_unit':'don_vi_mua',
    'wind_speed_unit':'don_vi_gio','interval_seconds':'chu_ky_giay',
    'bike_observation_id':'ma_mau_xe','weather_observation_id':'ma_mau_thoi_tiet',
    'service_name':'ten_dich_vu','heartbeat_at':'thoi_diem_tin_hieu_song','input_watermark':'moc_du_lieu_moi_nhat',
    'calculation_version':'phien_ban_tinh_toan','configuration_hash':'ma_bam_cau_hinh',
    'configuration':'cau_hinh','summary':'tom_tat','result_count':'so_ket_qua',
    'window_start':'bat_dau_khoang','window_end':'ket_thuc_khoang','aggregation':'kieu_tong_hop',
    'metric_name':'ten_chi_so','metric_value':'gia_tri_chi_so','sample_count':'so_mau',
    'observed_sample_count':'so_mau_quan_sat','expected_sample_count':'so_mau_ky_vong','coverage':'do_phu',
    'dimensions':'thuoc_tinh_phan_tich','input_cutoff':'gioi_han_du_lieu','calculated_at':'thoi_diem_tinh_toan',
    'service_run_id':'ma_luot_chay_dich_vu','run_date':'ngay_chay','algorithm':'thuat_toan',
    'feature_config':'cau_hinh_dac_trung','parameters':'tham_so','clustering_run_id':'ma_luot_phan_cum',
    'cluster_label':'nhan_nhom','distance_to_centroid':'khoang_cach_den_tam','feature_values':'gia_tri_dac_trung',
    'metadata_snapshot':'thong_tin_tai_thoi_diem','profile':'ho_so','kind':'loai','identity_hash':'ma_bam_dinh_danh',
    'created_at':'tao_luc','trained_at':'huan_luyen_luc','train_start':'bat_dau_du_lieu_hoc',
    'train_end':'ket_thuc_du_lieu_hoc','metrics':'danh_gia','artifact':'du_lieu_mo_hinh','is_active':'dang_su_dung',
    'requested_at':'thoi_diem_yeu_cau','model_version_id':'ma_phien_ban_mo_hinh',
    'input_cutoff_at':'gioi_han_du_lieu','input_time':'thoi_diem_dau_vao','target_at':'thoi_diem_muc_tieu',
    'issued_at':'thoi_diem_phat_hanh','input_observation_id':'ma_mau_dau_vao','reason':'ly_do',
    'raw_predicted_bikes':'so_xe_du_doan_goc','predicted_bikes':'so_xe_du_doan','features':'dac_trung',
    'actual_observation_id':'ma_mau_thuc_te','evaluated_at':'thoi_diem_danh_gia','actual_bikes':'so_xe_thuc_te',
    'actual_time':'thoi_diem_thuc_te','target_offset_seconds':'lech_moc_muc_tieu_giay',
    'absolute_error':'sai_so_tuyet_doi','squared_error':'sai_so_binh_phuong',
    'served_absolute_error':'sai_so_tuyet_doi_hien_thi',
}


def db_table(logical):
    return TABLE_NAMES[logical] if LANGUAGE=='vietnamese' else logical


def db_column(logical,*args,**kwargs):
    return mapped_column(COLUMN_NAMES[logical] if LANGUAGE=='vietnamese' else logical,
        *args,key=logical,**kwargs)


def db_foreign(reference):
    table,column=reference.split('.')
    # ForeignKey resolves the column by its stable key; the compiler emits its physical name.
    return db_table(table)+'.'+column


def db_check(expression,**kwargs):
    if LANGUAGE=='vietnamese':
        # SQL string literals are deliberately left untouched.
        expression=re.sub(r"'(?:''|[^'])*'|\b[a-z_][a-z_0-9]*\b",
            lambda m:m[0] if m[0].startswith("'") else COLUMN_NAMES.get(m[0],m[0]),expression)
    return CheckConstraint(expression,**kwargs)
