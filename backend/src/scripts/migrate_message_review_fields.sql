-- Migration: Add specialist review fields to messages table
-- Run against your PostgreSQL database after deploying the updated models.
--
-- These columns track per-message specialist review outcomes so that
-- "request changes" marks only the AI message (not the chat) as rejected
-- and allows regeneration.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS review_status  VARCHAR;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS review_feedback TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS reviewed_at     TIMESTAMP;

-- Add the new notification type to the enum (if using native PG enum).
-- If the column uses VARCHAR / non-native enum, this step is not needed.
-- ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'chat_revision';
