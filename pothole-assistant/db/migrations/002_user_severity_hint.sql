ALTER TABLE pothole_report
ADD COLUMN IF NOT EXISTS user_severity_hint VARCHAR(10)
CHECK (user_severity_hint IN ('low', 'medium', 'high', 'critical'));
