# T?n b?ng v? c?t ti?ng Vi?t

12 b?ng nghi?p v? ???c ??i t?n v?t l? sang ti?ng Vi?t kh?ng d?u t?i migration `0007_vietnamese_names`. B?ng k? thu?t `alembic_version` gi? nguy?n ?? c?ng c? migration ho?t ??ng.

C?c t?n c? l? VIEW ??n b?ng, c?p nh?t ???c tr?n MySQL, d?nh cho l?ch GitHub c?n d?ng b?n m? c?. VIEW kh?ng nh?n b?n d? li?u. Python v? h?p ??ng JSON API gi? kh?a l?p tr?nh c? qua `shared/database_names.py`.

| T?n c? | B?ng v?t l? m?i |
|---|---|
| `collection_runs` | `luot_thu_thap` |
| `model_versions` | `phien_ban_mo_hinh` |
| `service_runs` | `luot_chay_dich_vu` |
| `stations` | `tram_xe` |
| `analysis_results` | `ket_qua_phan_tich` |
| `bike_observations` | `lich_su_so_xe` |
| `clustering_runs` | `luot_phan_cum` |
| `training_jobs` | `luot_huan_luyen` |
| `weather_observations` | `lich_su_thoi_tiet` |
| `observation_weather_links` | `lien_ket_xe_thoi_tiet` |
| `predictions` | `du_doan_so_xe` |
| `station_clusters` | `nhom_tram` |

## Ki?m tra l?ch s? th?ng 10

```sql
SELECT ma_tram, thoi_diem_mau, so_xe_co_the_thue, chat_luong_du_lieu
FROM lich_su_so_xe
WHERE nguon = 'citibike_historical'
ORDER BY thoi_diem_mau DESC
LIMIT 30;
```

## Th?c hi?n v? ki?m ch?ng

`python -m scripts.migrate_vietnamese_database --apply` gi? kh?a c?c d?ch v?, sao l?u schema v? to?n b? d?ng d? li?u v?o `artifacts/schema_rename/<th?i ?i?m>/`, ??i t?n b?ng DDL r?i so s?nh s? d?ng v? SHA256 c?a t?ng b?ng. Ch? ghi revision m?i sau khi d? li?u kh?p ho?n to?n.

C?ng c? n?y d?nh cho qu?n tr? khi d?ch v? ???c t?m d?ng. DDL MySQL kh?ng rollback nh? giao d?ch d? li?u; c?n gi? b?n sao l?u v? migration ??o t?n. Kh?ng ch?y ??ng th?i v?i thay ??i schema kh?c.

`DATABASE_SCHEMA_LANGUAGE=vietnamese` ch?n t?n v?t l? m?i; `english` ch? d?nh cho m? chuy?n ti?p s? d?ng VIEW t??ng th?ch. Kh?ng ??i t?n kh?a JSON trong d? li?u l?ch s? ho?c gi? tr? tr?ng th?i nghi?p v?.

Migration c? th? ti?p t?c khi m?t ph?n t?n ?? ???c ??i. Khi ph?i ??o t?n, d?ng d?ch v?, chuy?n m? v? ch? ?? `english`, d?ng `python -m alembic downgrade 0006_prediction`, r?i ki?m ch?ng l?i tr??c khi m? l?ch. Kh?ng x?a d? li?u ?? ??o t?n.

## luot_thu_thap

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `scheduled_at` | `thoi_diem_lich` |
| `started_at` | `bat_dau_luc` |
| `finished_at` | `ket_thuc_luc` |
| `source` | `nguon` |
| `feed_metadata` | `thong_tin_nguon` |
| `bronze_manifest_path` | `duong_dan_manifest_bronze` |
| `status` | `trang_thai` |
| `success_count` | `so_thanh_cong` |
| `error_count` | `so_loi` |
| `attempt_count` | `so_lan_thu` |
| `error_summary` | `tom_tat_loi` |

## phien_ban_mo_hinh

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `source` | `nguon` |
| `name` | `ten` |
| `kind` | `loai` |
| `identity_hash` | `ma_bam_dinh_danh` |
| `created_at` | `tao_luc` |
| `trained_at` | `huan_luyen_luc` |
| `train_start` | `bat_dau_du_lieu_hoc` |
| `train_end` | `ket_thuc_du_lieu_hoc` |
| `feature_config` | `cau_hinh_dac_trung` |
| `metrics` | `danh_gia` |
| `artifact` | `du_lieu_mo_hinh` |
| `is_active` | `dang_su_dung` |

## luot_chay_dich_vu

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `service_name` | `ten_dich_vu` |
| `source` | `nguon` |
| `scheduled_at` | `thoi_diem_lich` |
| `started_at` | `bat_dau_luc` |
| `finished_at` | `ket_thuc_luc` |
| `heartbeat_at` | `thoi_diem_tin_hieu_song` |
| `input_watermark` | `moc_du_lieu_moi_nhat` |
| `status` | `trang_thai` |
| `attempt_count` | `so_lan_thu` |
| `calculation_version` | `phien_ban_tinh_toan` |
| `configuration_hash` | `ma_bam_cau_hinh` |
| `configuration` | `cau_hinh` |
| `summary` | `tom_tat` |
| `result_count` | `so_ket_qua` |
| `error_summary` | `tom_tat_loi` |

## tram_xe

| C?t c? | C?t v?t l? m?i |
|---|---|
| `source` | `nguon` |
| `station_id` | `ma_tram` |
| `name` | `ten` |
| `latitude` | `vi_do` |
| `longitude` | `kinh_do` |
| `rack_count` | `so_gia_xe` |
| `capacity` | `suc_chua` |
| `information_updated_at` | `thoi_diem_cap_nhat_thong_tin` |
| `is_monitored` | `dang_theo_doi` |
| `updated_at` | `cap_nhat_luc` |

## ket_qua_phan_tich

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `source` | `nguon` |
| `station_id` | `ma_tram` |
| `window_start` | `bat_dau_khoang` |
| `window_end` | `ket_thuc_khoang` |
| `aggregation` | `kieu_tong_hop` |
| `metric_name` | `ten_chi_so` |
| `metric_value` | `gia_tri_chi_so` |
| `sample_count` | `so_mau` |
| `observed_sample_count` | `so_mau_quan_sat` |
| `expected_sample_count` | `so_mau_ky_vong` |
| `coverage` | `do_phu` |
| `quality_status` | `chat_luong_du_lieu` |
| `dimensions` | `thuoc_tinh_phan_tich` |
| `input_cutoff` | `gioi_han_du_lieu` |
| `input_watermark` | `moc_du_lieu_moi_nhat` |
| `calculated_at` | `thoi_diem_tinh_toan` |
| `calculation_version` | `phien_ban_tinh_toan` |
| `configuration_hash` | `ma_bam_cau_hinh` |
| `service_run_id` | `ma_luot_chay_dich_vu` |

## lich_su_so_xe

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `source` | `nguon` |
| `station_id` | `ma_tram` |
| `collection_run_id` | `ma_luot_thu_thap` |
| `sampled_at` | `thoi_diem_mau` |
| `collected_at` | `thoi_diem_thu_thap` |
| `source_observed_at` | `thoi_diem_nguon` |
| `available_bikes` | `so_xe_co_the_thue` |
| `available_docks` | `so_cho_tra_xe` |
| `is_installed` | `da_lap_dat` |
| `is_renting` | `cho_phep_thue` |
| `is_returning` | `cho_phep_tra` |
| `feed_last_updated` | `thoi_diem_cap_nhat_nguon` |
| `gbfs_version` | `phien_ban_gbfs` |
| `quality_status` | `chat_luong_du_lieu` |

## luot_phan_cum

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `source` | `nguon` |
| `run_date` | `ngay_chay` |
| `service_run_id` | `ma_luot_chay_dich_vu` |
| `window_start` | `bat_dau_khoang` |
| `window_end` | `ket_thuc_khoang` |
| `input_cutoff` | `gioi_han_du_lieu` |
| `started_at` | `bat_dau_luc` |
| `finished_at` | `ket_thuc_luc` |
| `status` | `trang_thai` |
| `algorithm` | `thuat_toan` |
| `calculation_version` | `phien_ban_tinh_toan` |
| `configuration_hash` | `ma_bam_cau_hinh` |
| `feature_config` | `cau_hinh_dac_trung` |
| `parameters` | `tham_so` |
| `summary` | `tom_tat` |

## luot_huan_luyen

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `source` | `nguon` |
| `requested_at` | `thoi_diem_yeu_cau` |
| `started_at` | `bat_dau_luc` |
| `finished_at` | `ket_thuc_luc` |
| `status` | `trang_thai` |
| `parameters` | `tham_so` |
| `summary` | `tom_tat` |
| `model_version_id` | `ma_phien_ban_mo_hinh` |
| `error_summary` | `tom_tat_loi` |

## lich_su_thoi_tiet

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `collection_run_id` | `ma_luot_thu_thap` |
| `requested_latitude` | `vi_do_yeu_cau` |
| `requested_longitude` | `kinh_do_yeu_cau` |
| `returned_latitude` | `vi_do_tra_ve` |
| `returned_longitude` | `kinh_do_tra_ve` |
| `weather_time` | `thoi_diem_thoi_tiet` |
| `collected_at` | `thoi_diem_thu_thap` |
| `temperature` | `nhiet_do` |
| `humidity` | `do_am` |
| `rain` | `luong_mua` |
| `wind_speed` | `toc_do_gio` |
| `units` | `don_vi` |
| `temperature_unit` | `don_vi_nhiet_do` |
| `humidity_unit` | `don_vi_do_am` |
| `rain_unit` | `don_vi_mua` |
| `wind_speed_unit` | `don_vi_gio` |
| `interval_seconds` | `chu_ky_giay` |
| `source` | `nguon` |

## lien_ket_xe_thoi_tiet

| C?t c? | C?t v?t l? m?i |
|---|---|
| `bike_observation_id` | `ma_mau_xe` |
| `weather_observation_id` | `ma_mau_thoi_tiet` |

## du_doan_so_xe

| C?t c? | C?t v?t l? m?i |
|---|---|
| `id` | `ma` |
| `source` | `nguon` |
| `station_id` | `ma_tram` |
| `service_run_id` | `ma_luot_chay_dich_vu` |
| `scheduled_at` | `thoi_diem_lich` |
| `input_cutoff_at` | `gioi_han_du_lieu` |
| `input_time` | `thoi_diem_dau_vao` |
| `target_at` | `thoi_diem_muc_tieu` |
| `issued_at` | `thoi_diem_phat_hanh` |
| `input_observation_id` | `ma_mau_dau_vao` |
| `model_version_id` | `ma_phien_ban_mo_hinh` |
| `status` | `trang_thai` |
| `reason` | `ly_do` |
| `raw_predicted_bikes` | `so_xe_du_doan_goc` |
| `predicted_bikes` | `so_xe_du_doan` |
| `features` | `dac_trung` |
| `actual_observation_id` | `ma_mau_thuc_te` |
| `evaluated_at` | `thoi_diem_danh_gia` |
| `actual_bikes` | `so_xe_thuc_te` |
| `actual_time` | `thoi_diem_thuc_te` |
| `target_offset_seconds` | `lech_moc_muc_tieu_giay` |
| `absolute_error` | `sai_so_tuyet_doi` |
| `squared_error` | `sai_so_binh_phuong` |
| `served_absolute_error` | `sai_so_tuyet_doi_hien_thi` |

## nhom_tram

| C?t c? | C?t v?t l? m?i |
|---|---|
| `source` | `nguon` |
| `clustering_run_id` | `ma_luot_phan_cum` |
| `station_id` | `ma_tram` |
| `cluster_label` | `nhan_nhom` |
| `distance_to_centroid` | `khoang_cach_den_tam` |
| `feature_values` | `gia_tri_dac_trung` |
| `metadata_snapshot` | `thong_tin_tai_thoi_diem` |
| `sample_count` | `so_mau` |
| `expected_sample_count` | `so_mau_ky_vong` |
| `coverage` | `do_phu` |
| `profile` | `ho_so` |
