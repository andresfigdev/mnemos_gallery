BEGIN;

CREATE TABLE IF NOT EXISTS folder_nodes (
    id BIGSERIAL PRIMARY KEY,
    folder_root_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    parent_node_id BIGINT NULL REFERENCES folder_nodes(id) ON DELETE CASCADE,
    rel_path TEXT NOT NULL,
    name TEXT NOT NULL,
    depth INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_folder_nodes_root_rel_path UNIQUE (folder_root_id, rel_path)
);

CREATE INDEX IF NOT EXISTS idx_folder_nodes_root_id ON folder_nodes(folder_root_id);
CREATE INDEX IF NOT EXISTS idx_folder_nodes_parent_id ON folder_nodes(parent_node_id);

CREATE TABLE IF NOT EXISTS folder_tags (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS folder_node_tags (
    folder_node_id BIGINT NOT NULL REFERENCES folder_nodes(id) ON DELETE CASCADE,
    tag_id BIGINT NOT NULL REFERENCES folder_tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (folder_node_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_folder_node_tags_tag_id ON folder_node_tags(tag_id);

ALTER TABLE images
    ADD COLUMN IF NOT EXISTS folder_node_id BIGINT NULL REFERENCES folder_nodes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_images_folder_node_id ON images(folder_node_id);

COMMIT;
