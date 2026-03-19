CREATE TABLE IF NOT EXISTS analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  custom_name VARCHAR(255),
  company_name VARCHAR(255) NOT NULL,
  complexity_tier VARCHAR(20) DEFAULT 'standard',
  status VARCHAR(50) DEFAULT 'pending',
  last_completed_agent VARCHAR(100),
  lead_plan JSONB,
  harvester_output JSONB,
  parser_output JSONB,
  scenario_output JSONB,
  recommendation_output JSONB,
  judge_output JSONB,
  final_report JSONB,
  flags JSONB,
  ifa_confirmed_flags JSONB,
  export_locked BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW(),
  saved BOOLEAN DEFAULT false,
  saved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analyses(id),
  agent_name VARCHAR(100),
  status VARCHAR(50),
  input_reference VARCHAR(255),
  output_reference VARCHAR(255),
  retry_count INTEGER DEFAULT 0,
  error_message TEXT,
  token_count INTEGER,
  tool_calls_count INTEGER,
  started_at TIMESTAMP,
  completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS checkpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID REFERENCES analyses(id),
  agent_name VARCHAR(100),
  checkpoint_data JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_improvements (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name VARCHAR(100),
  failure_pattern TEXT,
  suggested_prompt_addition TEXT,
  occurrence_count INTEGER DEFAULT 1,
  detected_at TIMESTAMP DEFAULT NOW(),
  applied BOOLEAN DEFAULT false,
  applied_at TIMESTAMP
);
