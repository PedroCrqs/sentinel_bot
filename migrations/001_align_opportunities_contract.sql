-- Additive contract alignment for the existing public.opportunities table.
-- Existing rows remain untouched; new semantic IDs are nullable until the
-- matching projection is migrated to Demanda x Oferta.

ALTER TABLE public.opportunities
    ADD COLUMN IF NOT EXISTS seller_message_id VARCHAR,
    ADD COLUMN IF NOT EXISTS demand_id VARCHAR,
    ADD COLUMN IF NOT EXISTS offer_id VARCHAR,
    ADD COLUMN IF NOT EXISTS match_details JSONB,
    ADD COLUMN IF NOT EXISTS rule_version VARCHAR NOT NULL DEFAULT 'v1';

-- save_opportunities() uses this conflict target for message-based
-- compatibility. PostgreSQL permits multiple NULLs, so old/incomplete rows
-- are not rewritten or collapsed by this index.
CREATE UNIQUE INDEX IF NOT EXISTS uq_opportunities_buyer_seller
    ON public.opportunities (buyer_message_id, seller_message_id);

CREATE INDEX IF NOT EXISTS idx_opportunities_dispatch
    ON public.opportunities (dispatch_status);
