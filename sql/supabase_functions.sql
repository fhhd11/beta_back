-- Supabase functions for efficient user profile and LiteLLM key retrieval
-- These functions should be created in your Supabase database

-- Function to get user's LiteLLM key
CREATE OR REPLACE FUNCTION get_user_litellm_key(user_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
BEGIN
    -- Query user profiles table for LiteLLM key
    SELECT json_build_object(
        'litellm_key', up.litellm_key,
        'user_id', up.id,
        'email', up.email,
        'created_at', up.created_at,
        'updated_at', up.updated_at
    )
    INTO result
    FROM user_profiles up
    WHERE up.id = user_id
    AND up.litellm_key IS NOT NULL
    AND up.litellm_key != '';
    
    -- Return the result or null if not found
    RETURN COALESCE(result, NULL);
END;
$$;

-- Function to get complete user profile data
CREATE OR REPLACE FUNCTION get_user_profile(user_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
BEGIN
    -- Query user profiles table for complete profile
    SELECT json_build_object(
        'id', up.id,
        'email', up.email,
        'name', up.name,
        'litellm_key', up.litellm_key,
        'letta_agent_id', up.letta_agent_id,
        'agent_status', up.agent_status,
        'created_at', up.created_at,
        'updated_at', up.updated_at,
        'metadata', up.metadata,
        'profile_exists', true
    )
    INTO result
    FROM user_profiles up
    WHERE up.id = user_id;
    
    -- Return the result or null if not found
    RETURN COALESCE(result, NULL);
END;
$$;

-- Function to get user profile with agents list
CREATE OR REPLACE FUNCTION get_user_profile_with_agents(user_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result JSON;
    agents_json JSON;
BEGIN
    -- Get agent instances for the user (using correct table name)
    SELECT COALESCE(json_agg(
        json_build_object(
            'agent_id', ai.agent_id,
            'template_id', ai.template_id,
            'version', ai.version,
            'created_at', ai.created_at,
            'updated_at', ai.updated_at
        )
    ), '[]'::json)
    INTO agents_json
    FROM agent_instances ai
    WHERE ai.user_id = user_id;
    
    -- Get user profile with agents
    SELECT json_build_object(
        'id', up.id,
        'email', up.email,
        'name', up.name,
        'litellm_key', up.litellm_key,
        'letta_agent_id', up.letta_agent_id,
        'agent_status', up.agent_status,
        'created_at', up.created_at,
        'updated_at', up.updated_at,
        'metadata', up.metadata,
        'agents', agents_json,
        'profile_exists', true
    )
    INTO result
    FROM user_profiles up
    WHERE up.id = user_id;
    
    -- Return the result or null if not found
    RETURN COALESCE(result, NULL);
END;
$$;

-- Grant execute permissions to authenticated users
GRANT EXECUTE ON FUNCTION get_user_litellm_key(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_profile(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_profile_with_agents(UUID) TO authenticated;

-- Grant execute permissions to service role (for service key access)
GRANT EXECUTE ON FUNCTION get_user_litellm_key(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION get_user_profile(UUID) TO service_role;
GRANT EXECUTE ON FUNCTION get_user_profile_with_agents(UUID) TO service_role;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_profiles_id ON user_profiles(id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_litellm_key ON user_profiles(id) WHERE litellm_key IS NOT NULL AND litellm_key != '';
CREATE INDEX IF NOT EXISTS idx_agent_instances_user_id ON agent_instances(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_instances_agent_id ON agent_instances(agent_id);

-- Optional: Create a view for easier querying
CREATE OR REPLACE VIEW user_profiles_with_agents AS
SELECT 
    up.*,
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
GRANT SELECT ON user_profiles_with_agents TO authenticated;
GRANT SELECT ON user_profiles_with_agents TO service_role;
