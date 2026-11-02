{{ config(tags = ['staging']) }}

-- TC-CAP-MG-EXCEL (phần staging; phần đọc tiêu đề hai dòng ở tests/loader):
--   1. Mọi dòng hợp lệ có đủ chỉ tiêu dạng số (số ghi dạng chữ '10,5' đã thành 10.5).
--   2. Mỗi ô lỗi công thức ở landing đi đúng vào __rejected với FORMULA_ERROR.
--   3. Không dòng hợp lệ nào thiếu người duyệt hoặc ngày duyệt (DQ-CHUADUYET).
-- Phép thử âm: đọc file với header_rows: 1 ở hợp đồng -> landing lệch cột, vế 1 hoặc 2 đỏ.

select batch_id, source_row_no, 'TARGET_NOT_NUMERIC' as problem
from {{ ref('stg_manual__kpi') }}
where target_new_clients is null or target_calls is null or target_aum_bil is null

union all

select batch_id, source_row_no, 'UNAPPROVED_ACCEPTED'
from {{ ref('stg_manual__kpi') }}
where approver is null or approved_date is null

union all

select l.batch_id, l.source_row_no, 'FORMULA_ERROR_NOT_REJECTED'
from {{ source('landing', 'manual_kpi') }} l
where (
        {{ stg_is_excel_error('l.target_new_clients') }}
        or {{ stg_is_excel_error('l.target_calls') }}
        or {{ stg_is_excel_error('l.target_aum_bil') }}
      )
  and not exists (
      select 1 from {{ ref('stg_manual__kpi__rejected') }} r
      where r.batch_id = l.batch_id and r.source_row_no = l.source_row_no
        and r.reason_code = 'FORMULA_ERROR'
  )
