BEGIN;

ALTER TABLE folder_nodes
    ADD COLUMN IF NOT EXISTS naming_base TEXT NULL,
    ADD COLUMN IF NOT EXISTS naming_number_width SMALLINT NULL;

COMMENT ON COLUMN folder_nodes.naming_base IS 'Base name for image naming (e.g. Alice); NULL or empty disables rename';
COMMENT ON COLUMN folder_nodes.naming_number_width IS 'Zero-padded width for sequence number (e.g. 4 -> 0001); NULL disables rename';

COMMIT;
