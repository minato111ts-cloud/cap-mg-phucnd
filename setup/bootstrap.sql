\encoding UTF8
\set ON_ERROR_STOP on

-- 1. Tạo 2 role chức năng NOLOGIN (chạy lại nhiều lần không lỗi, không đặt password)
DO $do$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finova_loader') THEN
        CREATE ROLE finova_loader NOLOGIN;
    ELSE
        ALTER ROLE finova_loader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finova_dbt') THEN
        CREATE ROLE finova_dbt NOLOGIN;
    ELSE
        ALTER ROLE finova_dbt NOLOGIN;
    END IF;
END
$do$;

-- Cho phép postgres SET ROLE sang 2 role này
GRANT finova_loader, finova_dbt TO postgres;

-- 2. Tạo 6 schema
CREATE SCHEMA IF NOT EXISTS landing;
CREATE SCHEMA IF NOT EXISTS ctrl;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS atomic;
CREATE SCHEMA IF NOT EXISTS asof;
CREATE SCHEMA IF NOT EXISTS mart;

-- 3. Thu hồi quyền mặc định để đảm bảo đúng 18 ô quyền ở Bảng 13
REVOKE CREATE ON SCHEMA public FROM PUBLIC, finova_loader, finova_dbt;
REVOKE ALL ON SCHEMA landing, ctrl, staging, atomic, asof, mart FROM PUBLIC, finova_loader, finova_dbt;

-- 4. Cấp quyền theo ma trận Bảng 13
-- Schema landing: loader có USAGE, CREATE; dbt chỉ có USAGE
GRANT USAGE, CREATE ON SCHEMA landing TO finova_loader;
GRANT USAGE ON SCHEMA landing TO finova_dbt;

-- Schema ctrl: cả hai role đều có USAGE, CREATE
GRANT USAGE, CREATE ON SCHEMA ctrl TO finova_loader, finova_dbt;

-- Các schema transform: chỉ finova_dbt có USAGE, CREATE
GRANT USAGE, CREATE ON SCHEMA staging, atomic, asof, mart TO finova_dbt;

-- 5. Default privileges để bảng tạo về sau tự động có quyền đọc chéo
-- Bảng trong landing do finova_loader tạo -> finova_dbt đọc được (SELECT)
ALTER DEFAULT PRIVILEGES FOR ROLE finova_loader IN SCHEMA landing
    GRANT SELECT ON TABLES TO finova_dbt;

-- Bảng trong ctrl do role này tạo -> role kia đọc được (SELECT)
ALTER DEFAULT PRIVILEGES FOR ROLE finova_loader IN SCHEMA ctrl
    GRANT SELECT ON TABLES TO finova_dbt;
ALTER DEFAULT PRIVILEGES FOR ROLE finova_dbt IN SCHEMA ctrl
    GRANT SELECT ON TABLES TO finova_loader;

