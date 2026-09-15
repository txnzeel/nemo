-- REVIEWED TEMPLATE ONLY; never executed by NEMO automatically.
-- An authorized administrator must review object names, compute costs and grants.
-- Raw ingestion into Snowflake is not implemented. Never use SYSADMIN in the application.
use role SYSADMIN;
create warehouse if not exists NEMO_XS
    warehouse_size = 'XSMALL' auto_suspend = 60 auto_resume = true initially_suspended = true;
create database if not exists NEMO;
create schema if not exists NEMO.RAW;
create schema if not exists NEMO.STAGING;
create schema if not exists NEMO.INTERMEDIATE;
create schema if not exists NEMO.ANALYTICS;

use role SECURITYADMIN;
create role if not exists NEMO_INGEST;
create role if not exists NEMO_TRANSFORM;
create role if not exists NEMO_ANALYST;
grant role NEMO_INGEST to role SYSADMIN;
grant role NEMO_TRANSFORM to role SYSADMIN;
grant role NEMO_ANALYST to role SYSADMIN;
grant usage on warehouse NEMO_XS to role NEMO_INGEST;
grant usage on warehouse NEMO_XS to role NEMO_TRANSFORM;
grant usage on warehouse NEMO_XS to role NEMO_ANALYST;
grant usage on database NEMO to role NEMO_INGEST;
grant usage on database NEMO to role NEMO_TRANSFORM;
grant usage on database NEMO to role NEMO_ANALYST;
grant usage on schema NEMO.RAW to role NEMO_INGEST;
grant create table on schema NEMO.RAW to role NEMO_INGEST;
grant select, insert, update, delete on all tables in schema NEMO.RAW to role NEMO_INGEST;
grant select, insert, update, delete on future tables in schema NEMO.RAW to role NEMO_INGEST;
grant usage on schema NEMO.RAW to role NEMO_TRANSFORM;
grant select on all tables in schema NEMO.RAW to role NEMO_TRANSFORM;
grant select on future tables in schema NEMO.RAW to role NEMO_TRANSFORM;
grant usage, create table, create view on schema NEMO.STAGING to role NEMO_TRANSFORM;
grant usage, create table, create view on schema NEMO.INTERMEDIATE to role NEMO_TRANSFORM;
grant usage, create table, create view on schema NEMO.ANALYTICS to role NEMO_TRANSFORM;
grant usage on schema NEMO.ANALYTICS to role NEMO_ANALYST;
grant select on all tables in schema NEMO.ANALYTICS to role NEMO_ANALYST;
grant select on future tables in schema NEMO.ANALYTICS to role NEMO_ANALYST;
grant select on all views in schema NEMO.ANALYTICS to role NEMO_ANALYST;
grant select on future views in schema NEMO.ANALYTICS to role NEMO_ANALYST;
-- User-to-role assignment is deliberately an administrator's explicit deployment step.
