-- Owned inventory offers do not have rows in public.raw_messages
-- (their seller_message_id is synthetic: 'self-<property_id>').
-- Relax the foreign key to allow saving opportunities involving owned inventory.

ALTER TABLE public.opportunities
    DROP CONSTRAINT IF EXISTS opportunities_seller_message_id_fkey;
