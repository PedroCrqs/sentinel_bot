-- External WhatsApp offers do not have rows in public.imoveis.
-- Keep matched_imovel_id as nullable legacy metadata for owned inventory,
-- but do not enforce an FK that rejects external offers.

ALTER TABLE public.opportunities
    DROP CONSTRAINT IF EXISTS opportunities_matched_imovel_id_fkey;

ALTER TABLE public.opportunities
    ALTER COLUMN matched_imovel_id DROP NOT NULL;
