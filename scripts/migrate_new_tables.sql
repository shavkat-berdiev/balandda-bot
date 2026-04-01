-- Migration script for new structured reporting tables
-- Run this on the VPS PostgreSQL before deploying the new code
-- These enum types and tables support the button-driven report flow

-- ━━━ New ENUM types ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DO $$ BEGIN
    CREATE TYPE propertytype AS ENUM (
        'CHALET_WITH_SAUNA', 'CHALET_WITHOUT_SAUNA', 'WHITE_CHALET',
        'APARTMENT', 'PENTHOUSE', 'VILLA', 'SPA_SUITE'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE servicetype AS ENUM (
        'CLASSIC_AROMA_45', 'CLASSIC_AROMA_60', 'DETOX_60', 'DETOX_95',
        'FOOT_MASSAGE_30', 'BACK_MASSAGE_30', 'HAMMAM', 'OTHER_SERVICE'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE discounttype AS ENUM ('PERCENTAGE', 'FIXED_AMOUNT');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE discountreason AS ENUM (
        'BIRTHDAY', 'VIP_GUEST', 'PROMOTION', 'STAFF_REFERRAL', 'OTHER'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE reportstatus AS ENUM ('DRAFT', 'SUBMITTED', 'APPROVED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Add new values to existing expensecategory enum if missing
DO $$ BEGIN
    ALTER TYPE expensecategory ADD VALUE IF NOT EXISTS 'SALARY';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE expensecategory ADD VALUE IF NOT EXISTS 'REPAIR';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TYPE expensecategory ADD VALUE IF NOT EXISTS 'DELIVERY';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ━━━ New Tables ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE TABLE IF NOT EXISTS properties (
    id SERIAL PRIMARY KEY,
    code VARCHAR(20) UNIQUE NOT NULL,
    name_ru VARCHAR(100) NOT NULL,
    name_uz VARCHAR(100) NOT NULL,
    property_type propertytype NOT NULL,
    unit_number VARCHAR(10),
    capacity INTEGER NOT NULL,
    has_sauna BOOLEAN DEFAULT FALSE,
    price_weekday NUMERIC(15, 2) NOT NULL,
    price_weekend NUMERIC(15, 2) NOT NULL,
    emoji VARCHAR(10) DEFAULT '🏠',
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    business_unit businessunit DEFAULT 'RESORT'
);

CREATE INDEX IF NOT EXISTS idx_properties_code ON properties (code);

CREATE TABLE IF NOT EXISTS service_items (
    id SERIAL PRIMARY KEY,
    service_type servicetype NOT NULL,
    name_ru VARCHAR(100) NOT NULL,
    name_uz VARCHAR(100) NOT NULL,
    duration_minutes INTEGER NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS minibar_items (
    id SERIAL PRIMARY KEY,
    name_ru VARCHAR(100) NOT NULL,
    name_uz VARCHAR(100) NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS staff_members (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    role_description VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS structured_reports (
    id SERIAL PRIMARY KEY,
    report_date DATE NOT NULL,
    business_unit businessunit NOT NULL,
    status reportstatus DEFAULT 'DRAFT',
    submitted_by BIGINT NOT NULL,
    total_income NUMERIC(15, 2) DEFAULT 0,
    total_expense NUMERIC(15, 2) DEFAULT 0,
    previous_balance NUMERIC(15, 2) DEFAULT 0,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_structured_reports_date ON structured_reports (report_date);

CREATE TABLE IF NOT EXISTS income_entries (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES structured_reports(id) ON DELETE CASCADE,
    property_id INTEGER REFERENCES properties(id),
    service_item_id INTEGER REFERENCES service_items(id),
    minibar_item_id INTEGER REFERENCES minibar_items(id),
    payment_method paymentmethod NOT NULL,
    amount NUMERIC(15, 2) NOT NULL,
    quantity INTEGER DEFAULT 1,
    num_days INTEGER DEFAULT 1,
    discount_type discounttype,
    discount_value NUMERIC(15, 2),
    discount_reason discountreason,
    discount_note VARCHAR(255),
    note TEXT
);

CREATE TABLE IF NOT EXISTS expense_entries (
    id SERIAL PRIMARY KEY,
    report_id INTEGER NOT NULL REFERENCES structured_reports(id) ON DELETE CASCADE,
    expense_category expensecategory NOT NULL,
    staff_member_id INTEGER REFERENCES staff_members(id),
    amount NUMERIC(15, 2) NOT NULL,
    description VARCHAR(255) NOT NULL,
    note TEXT
);
