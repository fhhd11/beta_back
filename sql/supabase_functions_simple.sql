-- Simplified Supabase functions that work with existing tables
-- Use this version if you don't want to create custom functions

-- The functions below are optional and can be replaced with direct REST API calls
-- Our SupabaseClient now uses direct REST API calls instead of custom functions

-- Optional: Simple function to get user LiteLLM key (if you prefer functions over REST API)
CREATE OR REPLACE FUNCTION get_user_litellm_key_simple(user_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    litellm_key TEXT;
BEGIN
    SELECT up.litellm_key
    INTO litellm_key
    FROM user_profiles up
    WHERE up.id = user_id
    AND up.litellm_key IS NOT NULL
    AND up.litellm_key != '';
    
    RETURN litellm_key;
END;
$$;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION get_user_litellm_key_simple(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_litellm_key_simple(UUID) TO service_role;

-- Create indexes for better performance (these are the important ones)
CREATE INDEX IF NOT EXISTS idx_user_profiles_id ON user_profiles(id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_litellm_key ON user_profiles(id) WHERE litellm_key IS NOT NULL AND litellm_key != '';
CREATE INDEX IF NOT EXISTS idx_agent_instances_user_id ON agent_instances(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_instances_agent_id ON agent_instances(agent_id);

-- Optional: Create a simple view for user profiles with agents
CREATE OR REPLACE VIEW user_profiles_with_agents_simple AS
SELECT 
    up.id,
    up.email,
    up.name,
    up.litellm_key,
    up.letta_agent_id,
    up.agent_status,
    up.created_at,
    up.updated_at,
    up.metadata,
    COALESCE(
        (SELECT json_agg(
            json_build_object(
                'agent_id', ai.agent_id,
                'template_id', ai.template_id,
                'version', ai.version,
                'created_at', ai.created_at,
                'updated_at', ai.updated_at
            )
        )
        FROM agent_instances ai
        WHERE ai.user_id = up.id), 
        '[]'::json
    ) as agents
FROM user_profiles up;

-- Grant select permissions on the view
GRANT SELECT ON user_profiles_with_agents_simple TO authenticated;
GRANT SELECT ON user_profiles_with_agents_simple TO service_role;

-- Note: Our optimized SupabaseClient uses direct REST API calls instead of these functions
-- This provides better performance and simpler implementation
