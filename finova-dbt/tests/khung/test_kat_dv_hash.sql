-- Singular test kiểm tra dv_hash với 4 giá trị KAT ở Bảng 14 (KHUNG-KAT, KHUNG-KAT-HAIPHIEN)
with kat_cases as (
    select
        'KAT-TEXT' as kat_code,
        encode({{ dv_hash(["'FLEX'", "'C000001'"]) }}, 'hex') as actual_hex,
        '702d2794074a27d48f387cfe10f99f4c97fff8854e10c6d3cc55d4e23255a26e' as expected_hex
    union all
    select
        'KAT-NULL-A' as kat_code,
        encode({{ dv_hash(["'a'", "null::text", "'b'"]) }}, 'hex') as actual_hex,
        'a253ca2c12cce16b4200302bead4c0b959f748efca6ac9cf172f658163bdd572' as expected_hex
    union all
    select
        'KAT-NULL-B' as kat_code,
        encode({{ dv_hash(["'a'", "'b'", "null::text"]) }}, 'hex') as actual_hex,
        '0dfa42fcc5a8d44235a14844b51c63e242a7c0192bd72dd63e9428298a46a548' as expected_hex
    union all
    select
        'KAT-MIX' as kat_code,
        encode({{ dv_hash([
            "'2026-04-17 22:00:00+07'::timestamptz",
            "'2026-04-17'::date",
            "1500000.5::numeric(18,2)",
            "true",
            "null::text",
            "'Nguyễn Văn A'"
        ]) }}, 'hex') as actual_hex,
        '53ba63f3ffe40dcdad0a177cdd25fb2033f5b29f8ab7551f6bf049bb15680a3f' as expected_hex
)
select *
from kat_cases
where actual_hex <> expected_hex
