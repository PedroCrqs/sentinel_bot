-- Sentinel-owned state for snapshot/diff inventory synchronization.
-- This migration does not alter the external public.imoveis contract.

CREATE TABLE IF NOT EXISTS public.inventory_sync_state (
    property_id INTEGER PRIMARY KEY,
    fingerprint VARCHAR(64) NOT NULL,
    source_status VARCHAR(32) NOT NULL,
    is_present BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
