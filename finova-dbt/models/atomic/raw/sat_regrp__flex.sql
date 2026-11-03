-- Satellite đơn vị từ FLEX, grain: (regrp_hk, ingested_ts). Mẫu T-SAT.
-- Phiên bản G5/G6 tạo vòng ở CAP-MG-0061 không vào đây (bị loại ở staging), nên phiên bản hiệu lực vẫn là cha CN3.
{{ dv_load_sat('regrp_hk', 'sat_regrp_hd', 'stg_flex__regrp', [
    'grpid', 'parentid', 'grpname', 'grplevel', 'effdate', 'status',
]) }}
