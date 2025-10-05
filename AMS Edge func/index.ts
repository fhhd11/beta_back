// Supabase Edge Function implementing the AMS routing logic.
// Updated to work with custom proxy service instead of Zuplo
// The function is intentionally implemented as a single entry point with
// an internal router to minimise cold starts, as required by the spec.
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.4";
import YAML from "npm:yaml@2.3.4";
import semver from "npm:semver@7.6.2";
// HTTP Status codes
const Status = {
  OK: 200,
  BadRequest: 400,
  NotFound: 404,
  Conflict: 409,
  InternalServerError: 500
};
const SUPABASE_URL = Deno.env.get("SUPABASE_URL");
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
const PROXY_SERVICE_URL = Deno.env.get("PROXY_SERVICE_URL") ?? "https://betaback-production.up.railway.app";
const LETTA_API_BASE_URL = Deno.env.get("LETTA_API_BASE_URL") ?? "https://api.letta.com";
const LETTA_API_KEY = Deno.env.get("LETTA_API_KEY");
if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
  console.error("Missing Supabase configuration");
}
if (!PROXY_SERVICE_URL) {
  console.error("Missing PROXY_SERVICE_URL configuration");
}
const supabase = SUPABASE_URL && SUPABASE_SERVICE_ROLE_KEY ? createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: {
    persistSession: false
  }
}) : null;
serve(async (req)=>{
  try {
    const url = new URL(req.url);
    let path = url.pathname;
    // Extract the last part of the path after the last slash from functions/v1/ams/
    const segments = path.split('/').filter(Boolean);
    const amsIndex = segments.findIndex((seg)=>seg === 'ams');
    if (amsIndex >= 0 && amsIndex < segments.length - 1) {
      // Take all segments after 'ams'
      path = segments.slice(amsIndex + 1).join('/');
    } else {
      // If structure is unexpected, take the entire path and clean prefixes
      path = path.replace(/^\/?(functions\/v1\/ams\/)?/, '').replace(/^\/?api\/v1\//, '');
    }
    const method = req.method.toUpperCase();
    console.log(`Request: ${method} ${url.pathname} -> processed path: ${path}`);
    if (path === "health" && method === "GET") {
      return await handleHealth();
    }
    if (!supabase) {
      return jsonResponse({
        error: "Supabase client not initialised"
      }, Status.InternalServerError);
    }
    if (path === "templates/validate" && method === "POST") {
      const bodyText = await req.text();
      return await handleValidateTemplate(bodyText);
    }
    if (path === "templates/publish" && method === "POST") {
      const idempotencyKey = req.headers.get("Idempotency-Key") ?? undefined;
      const bodyText = await req.text();
      return await handlePublishTemplate(bodyText, idempotencyKey);
    }
    if (path === "me" && method === "GET") {
      const userId = req.headers.get("X-User-Id");
      if (!userId) {
        return jsonResponse({
          error: "Missing user context"
        }, Status.BadRequest);
      }
      return await handleGetProfile(userId);
    }
    if (path === "agents/create" && method === "POST") {
      const idempotencyKey = req.headers.get("Idempotency-Key") ?? undefined;
      const payload = await req.json();
      const userId = req.headers.get("X-User-Id") ?? payload["user_id"];
      if (!userId) {
        return jsonResponse({
          error: "Missing user context"
        }, Status.BadRequest);
      }
      return await handleCreateAgent(payload, userId, idempotencyKey);
    }
    const upgradeMatch = path.match(/^agents\/(.+?)\/upgrade$/);
    if (upgradeMatch && method === "POST") {
      const idempotencyKey = req.headers.get("Idempotency-Key") ?? undefined;
      const payload = await req.json();
      const userId = req.headers.get("X-User-Id") ?? undefined;
      const agentId = upgradeMatch[1];
      return await handleUpgradeAgent(agentId, payload, userId, idempotencyKey);
    }
    return jsonResponse({
      error: "Not Found"
    }, Status.NotFound);
  } catch (error) {
    console.error("Unhandled error", error);
    return jsonResponse({
      error: "Internal Server Error"
    }, Status.InternalServerError);
  }
});
async function handleHealth() {
  const checks = {};
  if (supabase) {
    const { error } = await supabase.from("af_templates").select("id").limit(1);
    checks["database"] = error ? `error: ${error.message}` : "ok";
  } else {
    checks["database"] = "uninitialised";
  }
  // Check proxy service health
  if (PROXY_SERVICE_URL) {
    try {
      const healthResponse = await fetch(`${PROXY_SERVICE_URL}/health`, {
        method: "GET",
        signal: AbortSignal.timeout(5000)
      });
      checks["proxy_service"] = healthResponse.ok ? "ok" : `status: ${healthResponse.status}`;
    } catch (error) {
      checks["proxy_service"] = `error: ${error.message}`;
    }
  } else {
    checks["proxy_service"] = "missing configuration";
  }
  if (LETTA_API_KEY) {
    checks["letta_api_key"] = "ok";
  } else {
    checks["letta_api_key"] = "missing";
  }
  return jsonResponse({
    status: "ok",
    checks
  });
}
async function handleGetProfile(userId) {
  if (!supabase) {
    return jsonResponse({
      error: "Supabase client not initialised"
    }, Status.InternalServerError);
  }
  try {
    console.log("Fetching profile for user:", userId);
    // Get user profile from user_profiles table
    const { data: profile, error: profileError } = await supabase.from("user_profiles").select("*").eq("id", userId).maybeSingle();
    if (profileError) {
      console.error("Error fetching user profile:", profileError);
      throw profileError;
    }
    if (!profile) {
      // Profile doesn't exist, return empty profile
      return jsonResponse({
        id: userId,
        email: null,
        name: null,
        litellm_key: null,
        letta_agent_id: null,
        agent_status: null,
        created_at: null,
        updated_at: null,
        profile_exists: false
      });
    }
    // Get agent instances for this user if profile exists
    const { data: agents, error: agentsError } = await supabase.from("agent_instances").select("agent_id, template_id, version, created_at, updated_at").eq("user_id", userId).order("created_at", {
      ascending: false
    });
    if (agentsError) {
      console.log("Warning: Failed to fetch agent instances:", agentsError);
    }
    const response = {
      id: profile.id,
      email: profile.email,
      name: profile.name,
      litellm_key: profile.litellm_key,
      letta_agent_id: profile.letta_agent_id,
      agent_status: profile.agent_status,
      created_at: profile.created_at,
      updated_at: profile.updated_at,
      profile_exists: true,
      agents: agents ?? []
    };
    return jsonResponse(response);
  } catch (error) {
    console.error("Error in handleGetProfile:", error);
    return jsonResponse({
      error: error.message ?? "Internal Server Error"
    }, Status.InternalServerError);
  }
}
async function handleValidateTemplate(rawBody) {
  try {
    const { agentFile, format } = parseAgentFile(rawBody);
    const validation = await validateAgentFile(agentFile);
    return jsonResponse({
      format,
      validation
    });
  } catch (error) {
    return jsonResponse({
      error: error.message ?? String(error)
    }, Status.BadRequest);
  }
}
async function handlePublishTemplate(rawBody, idempotencyKey) {
  if (!supabase) {
    return jsonResponse({
      error: "Supabase client not initialised"
    }, Status.InternalServerError);
  }
  try {
    const { agentFile, raw, format } = parseAgentFile(rawBody);
    await ensureIdempotency(idempotencyKey, rawBody);
    const validation = await validateAgentFile(agentFile);
    if (!validation.valid) {
      return jsonResponse({
        error: "Validation failed",
        details: validation.errors
      }, Status.BadRequest);
    }
    const templateId = agentFile.template.id;
    const version = agentFile.template.version;
    const { data: existingVersions, error: listError } = await supabase.from("af_versions").select("version").eq("template_id", templateId);
    if (listError) throw listError;
    const semverResult = assessSemver(version, existingVersions?.map((v)=>v.version) ?? []);
    if (!semverResult.allowed) {
      return jsonResponse({
        error: semverResult.message
      }, Status.BadRequest);
    }
    const checksum = await sha256(raw);
    const { error: templateUpsertError } = await supabase.from("af_templates").upsert({
      id: templateId
    });
    if (templateUpsertError) throw templateUpsertError;
    const { error: insertError } = await supabase.from("af_versions").insert({
      template_id: templateId,
      version,
      af_source: raw,
      checksum,
      is_latest: true,
      published_by: validation.publishedBy ?? null
    });
    if (insertError) {
      if (insertError.code === "23505") {
        return jsonResponse({
          error: "Version already exists"
        }, Status.Conflict);
      }
      throw insertError;
    }
    const { error: resetLatestError } = await supabase.from("af_versions").update({
      is_latest: false
    }).eq("template_id", templateId).neq("version", version);
    if (resetLatestError) throw resetLatestError;
    await cacheAgentFile(templateId, version, raw);
    const response = {
      template_id: templateId,
      version,
      checksum,
      is_latest: true
    };
    return jsonResponse(response);
  } catch (error) {
    if (error instanceof IdempotencyError) {
      return jsonResponse({
        error: error.message
      }, Status.Conflict);
    }
    console.error("Publish template error", error);
    return jsonResponse({
      error: "Internal Server Error"
    }, Status.InternalServerError);
  }
}
async function handleCreateAgent(payload, userId, idempotencyKey) {
  if (!supabase) {
    return jsonResponse({
      error: "Supabase client not initialised"
    }, Status.InternalServerError);
  }
  console.log("=== Create Agent Debug ===");
  console.log("Payload:", JSON.stringify(payload, null, 2));
  console.log("User ID:", userId);
  console.log("Idempotency Key:", idempotencyKey);
  try {
    await ensureIdempotency(idempotencyKey, JSON.stringify({
      payload,
      userId
    }));
    console.log("Resolving template version...");
    const { template, raw } = await resolveTemplateVersion(payload.template_id, payload.version, payload.use_latest ?? false);
    console.log("Template resolved:", template.template.id, "version:", template.template.version);
    console.log("Validating template variables...");
    await validateTemplateVariables(template, payload.variables ?? {});
    console.log("Variables validated successfully");
    console.log("Building agent config from template...");
    const config = buildAgentConfigFromTemplate(template, userId);
    if (payload.agent_name) {
      config.name = payload.agent_name;
    }
    console.log("Agent config built:", JSON.stringify(config, null, 2));
    console.log("Creating Letta agent...");
    const agent = await createLettaAgent(config);
    console.log("Letta agent created successfully:", agent.id);
    console.log("Saving agent instance to database...");
    const { error: insertError } = await supabase.from("agent_instances").insert({
      agent_id: agent.id,
      user_id: userId,
      template_id: payload.template_id,
      version: template.template.version,
      variables: payload.variables ?? {}
    });
    if (insertError) {
      console.log("Database insert error:", insertError);
      throw insertError;
    }
    console.log("Agent instance saved to database");
    // Update user_profiles with letta_agent_id + set agent_status=registered
    console.log("Updating user profile with letta_agent_id and agent_status...");
    const { error: profileUpdateError } = await supabase.from("user_profiles").update({
      letta_agent_id: agent.id,
      agent_status: "registered",
      updated_at: new Date().toISOString()
    }).eq("id", userId);
    if (profileUpdateError) {
      console.log("Warning: Failed to update user profile:", profileUpdateError);
    // агент создан успешно — не валим весь процесс
    } else {
      console.log("User profile updated with letta_agent_id and agent_status=registered");
    }
    const checksum = await sha256(raw);
    console.log("=== Create Agent Success ===");
    return jsonResponse({
      agent,
      template_checksum: checksum
    });
  } catch (error) {
    console.log("=== Create Agent Error ===");
    console.log("Error:", error);
    console.log("Error message:", error.message);
    console.log("Error stack:", error.stack);
    if (error instanceof IdempotencyError) {
      return jsonResponse({
        error: error.message
      }, Status.Conflict);
    }
    return jsonResponse({
      error: error.message ?? "Internal Server Error"
    }, Status.InternalServerError);
  }
}
async function handleUpgradeAgent(agentId, payload, userId, idempotencyKey) {
  if (!supabase) {
    return jsonResponse({
      error: "Supabase client not initialised"
    }, Status.InternalServerError);
  }
  try {
    await ensureIdempotency(idempotencyKey, JSON.stringify({
      agentId,
      payload,
      userId
    }));
    const { data: instance, error: instanceError } = await supabase.from("agent_instances").select("*").eq("agent_id", agentId).maybeSingle();
    if (instanceError) throw instanceError;
    if (!instance) {
      return jsonResponse({
        error: "Agent not found"
      }, Status.NotFound);
    }
    if (userId && instance.user_id !== userId) {
      return jsonResponse({
        error: "Agent not found"
      }, Status.NotFound);
    }
    const { template: targetTemplate } = await resolveTemplateVersion(instance.template_id, payload.target_version, payload.use_latest ?? false);
    const currentAgent = await fetchLettaAgent(agentId);
    // Simplified structure for compatibility with the new API
    const currentConfig = {
      id: currentAgent.id,
      name: currentAgent.name,
      llm_config: currentAgent.llm_config,
      embedding_config: currentAgent.embedding_config
    };
    const migrations = targetTemplate.migrations ?? [];
    const plan = buildMigrationPlan(instance.version, targetTemplate.template.version, migrations);
    if (payload.dry_run !== false) {
      const { diff, warnings } = await performDryRun(plan, currentConfig, instance.user_id);
      await logMigration(agentId, instance.version, targetTemplate.template.version, true, plan, diff);
      return jsonResponse({
        plan,
        diff,
        warnings,
        dry_run: true
      });
    }
    if (payload.use_queue) {
      await enqueueUpgradeJob({
        agent_id: agentId,
        target_version: targetTemplate.template.version,
        user_id: instance.user_id
      });
      return jsonResponse({
        message: "Upgrade queued",
        agent_id: agentId,
        target_version: targetTemplate.template.version
      });
    }
    // Update agent to use new proxy endpoint
    const endpoint = `${PROXY_SERVICE_URL}/api/v1/agents/${instance.user_id}/proxy`;
    const updateConfig = {
      llm_config: {
        ...currentConfig.llm_config,
        model_endpoint: endpoint
      },
      embedding_config: {
        ...currentConfig.embedding_config,
        embedding_endpoint: endpoint
      }
    };
    await updateLettaAgent(agentId, updateConfig);
    const { error: updateInstanceError } = await supabase.from("agent_instances").update({
      version: targetTemplate.template.version,
      updated_at: new Date().toISOString()
    }).eq("agent_id", agentId);
    if (updateInstanceError) throw updateInstanceError;
    await logMigration(agentId, instance.version, targetTemplate.template.version, false, plan, null);
    return jsonResponse({
      plan,
      applied: true,
      new_version: targetTemplate.template.version
    });
  } catch (error) {
    if (error instanceof IdempotencyError) {
      return jsonResponse({
        error: error.message
      }, Status.Conflict);
    }
    console.error("Upgrade agent error", error);
    return jsonResponse({
      error: error.message ?? "Internal Server Error"
    }, Status.InternalServerError);
  }
}
function jsonResponse(data, status = Status.OK) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json"
    }
  });
}
function parseAgentFile(rawBody) {
  const raw = rawBody.trim();
  let agentFile;
  let format;
  if (raw.startsWith("{")) {
    format = "json";
    agentFile = JSON.parse(raw);
  } else {
    format = "yaml";
    agentFile = YAML.parse(raw);
  }
  return {
    agentFile,
    raw,
    format
  };
}
async function validateAgentFile(agentFile) {
  const errors = [];
  if (!agentFile.af_version) {
    errors.push("Missing af_version");
  }
  if (!agentFile.template?.id) {
    errors.push("Missing template.id");
  }
  if (!agentFile.template?.name) {
    errors.push("Missing template.name");
  }
  if (!agentFile.template?.version) {
    errors.push("Missing template.version");
  } else if (!semver.valid(agentFile.template.version)) {
    errors.push("template.version must be valid SemVer");
  }
  if (!agentFile.compat?.letta_min) {
    errors.push("Missing compat.letta_min");
  }
  if (!agentFile.engine?.model) {
    errors.push("Missing engine.model");
  }
  if (!agentFile.engine?.embedding) {
    errors.push("Missing engine.embedding");
  }
  if (!agentFile.persona?.system_prompt) {
    errors.push("Missing persona.system_prompt");
  }
  if (agentFile.migrations) {
    for (const migration of agentFile.migrations){
      if (!migration.from || !migration.to) {
        errors.push("Migration entries must include from and to versions");
      }
      if (migration.steps) {
        for (const step of migration.steps){
          if (step.type === "json_patch" && !step.patch) {
            errors.push(`Migration ${migration.from}->${migration.to} missing patch`);
          }
          if (step.type === "script" && !step.script?.code) {
            errors.push(`Migration ${migration.from}->${migration.to} missing script`);
          }
        }
      }
    }
  }
  return {
    valid: errors.length === 0,
    errors,
    publishedBy: undefined
  };
}
function assessSemver(nextVersion, existing) {
  if (existing.includes(nextVersion)) {
    return {
      allowed: false,
      message: "Version already published"
    };
  }
  const sorted = existing.filter((v)=>semver.valid(v)).sort(semver.rcompare);
  if (sorted.length === 0) {
    return {
      allowed: true
    };
  }
  const latest = sorted[0];
  if (semver.lt(nextVersion, latest)) {
    return {
      allowed: false,
      message: `Version ${nextVersion} is lower than latest ${latest}`
    };
  }
  return {
    allowed: true
  };
}
async function cacheAgentFile(templateId, version, raw) {
  if (!supabase) return;
  try {
    await supabase.storage.from("af-templates").upload(`${templateId}/${version}.af`, raw, {
      contentType: "application/x-yaml",
      upsert: true
    });
  } catch (error) {
    console.warn("Failed to cache Agent File", error);
  }
}
async function resolveTemplateVersion(templateId, version, useLatest = false) {
  if (!supabase) throw new Error("Supabase not initialised");
  let query = supabase.from("af_versions").select("template_id, version, af_source, migrations").eq("template_id", templateId);
  if (version) {
    query = query.eq("version", version);
  } else if (useLatest) {
    query = query.eq("is_latest", true);
  } else {
    throw new Error("Either version or use_latest must be provided");
  }
  const { data, error } = await query.maybeSingle();
  if (error) throw error;
  if (!data) throw new Error("Template version not found");
  const parsed = parseAgentFile(data.af_source).agentFile;
  return {
    template: parsed,
    raw: data.af_source
  };
}
function buildAgentConfigFromTemplate(agentFile, userId) {
  if (!PROXY_SERVICE_URL) throw new Error("Missing proxy service URL");
  // Use the new proxy endpoint path for Letta agents
  // Letta will automatically append /chat/completions to this URL
  const endpoint = `${PROXY_SERVICE_URL}/api/v1/agents/${userId}/proxy`;
  return {
    memory_blocks: [
      {
        label: "persona",
        value: agentFile.persona.system_prompt,
        limit: 5000
      },
      {
        label: "human",
        value: "You are interacting with a user through this agent.",
        limit: 5000
      }
    ],
    llm_config: {
      model: agentFile.engine.model,
      model_endpoint: endpoint,
      model_endpoint_type: "openai",
      context_window: 8192
    },
    embedding_config: {
      embedding_model: agentFile.engine.embedding,
      embedding_endpoint: endpoint,
      embedding_endpoint_type: "openai",
      embedding_dim: 1536
    },
    tools: [
      "send_message",
      "core_memory_append",
      "core_memory_replace",
      "archival_memory_insert",
      "archival_memory_search",
      "conversation_search"
    ],
    include_base_tools: true,
    include_multi_agent_tools: false
  };
}
async function validateTemplateVariables(agentFile, variables) {
  if (!agentFile.persona?.variables_schema) return;
  const schema = agentFile.persona.variables_schema;
  if (schema?.required) {
    const missing = schema.required.filter((key)=>!(key in variables));
    if (missing.length > 0) {
      throw new Error(`Missing required variables: ${missing.join(", ")}`);
    }
  }
}
async function createLettaAgent(config) {
  if (!LETTA_API_KEY) {
    throw new Error("Missing Letta API key");
  }
  const url = `${LETTA_API_BASE_URL}/v1/agents/`;
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${LETTA_API_KEY}`
  };
  console.log("=== Letta API Request Debug ===");
  console.log("URL:", url);
  console.log("Method: POST");
  console.log("Headers:", JSON.stringify(headers, null, 2));
  console.log("Config payload:", JSON.stringify(config, null, 2));
  console.log("LETTA_API_BASE_URL env:", LETTA_API_BASE_URL);
  console.log("LETTA_API_KEY present:", !!LETTA_API_KEY);
  console.log("LETTA_API_KEY length:", LETTA_API_KEY?.length);
  console.log("Proxy endpoint in config:", config.llm_config.model_endpoint);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(config)
    });
    console.log("=== Letta API Response Debug ===");
    console.log("Status:", response.status);
    console.log("Status Text:", response.statusText);
    console.log("Response Headers:", JSON.stringify(Object.fromEntries(response.headers.entries()), null, 2));
    const responseText = await response.text();
    console.log("Raw response body:", responseText);
    if (!response.ok) {
      console.log("=== Letta API Error ===");
      console.log("Request failed with status:", response.status);
      throw new Error(`Letta create agent failed: ${response.status} ${responseText}`);
    }
    const jsonResponse = JSON.parse(responseText);
    console.log("=== Letta API Success ===");
    console.log("Parsed response:", JSON.stringify(jsonResponse, null, 2));
    return jsonResponse;
  } catch (fetchError) {
    console.log("=== Letta API Fetch Error ===");
    console.log("Fetch error:", fetchError);
    console.log("Error message:", fetchError.message);
    console.log("Error stack:", fetchError.stack);
    throw fetchError;
  }
}
async function fetchLettaAgent(agentId) {
  if (!LETTA_API_KEY) throw new Error("Missing Letta API key");
  const response = await fetch(`${LETTA_API_BASE_URL}/v1/agents/${agentId}`, {
    headers: {
      Authorization: `Bearer ${LETTA_API_KEY}`
    }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to fetch agent ${agentId}: ${response.status} ${text}`);
  }
  return await response.json();
}
async function updateLettaAgent(agentId, config) {
  if (!LETTA_API_KEY) throw new Error("Missing Letta API key");
  const response = await fetch(`${LETTA_API_BASE_URL}/v1/agents/${agentId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${LETTA_API_KEY}`
    },
    body: JSON.stringify(config)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Failed to update agent ${agentId}: ${response.status} ${text}`);
  }
  return await response.json();
}
function buildMigrationPlan(currentVersion, targetVersion, migrations) {
  if (currentVersion === targetVersion) {
    return [];
  }
  const path = [];
  let version = currentVersion;
  const guard = new Set();
  while(version !== targetVersion){
    if (guard.has(version)) {
      throw new Error("Circular migration plan detected");
    }
    guard.add(version);
    const step = migrations.find((m)=>m.from === version);
    if (!step) {
      throw new Error(`No migration step found from ${version} towards ${targetVersion}`);
    }
    path.push(...step.steps);
    version = step.to;
  }
  return path;
}
async function performDryRun(plan, currentConfig, userId) {
  const warnings = [];
  const diff = [];
  // Use the new proxy endpoint
  const endpoint = `${PROXY_SERVICE_URL}/api/v1/agents/${userId}/proxy`;
  diff.push({
    op: "set",
    path: "/llm_config/model_endpoint",
    value: endpoint
  });
  diff.push({
    op: "set",
    path: "/embedding_config/embedding_endpoint",
    value: endpoint
  });
  for (const step of plan){
    if (step.type === "script") {
      warnings.push(`Script step executed in dry-run only: ${step.description ?? "no description"}`);
    }
  }
  return {
    diff,
    warnings,
    updatedConfig: currentConfig
  };
}
async function logMigration(agentId, fromVersion, toVersion, dryRun, plan, diff) {
  if (!supabase) return;
  const { error } = await supabase.from("agent_migrations").insert({
    agent_id: agentId,
    from_version: fromVersion,
    to_version: toVersion,
    dry_run: dryRun,
    plan,
    diff,
    status: dryRun ? "dry_run" : "applied"
  });
  if (error) {
    console.warn("Failed to log migration", error);
  }
}
async function enqueueUpgradeJob(job) {
  if (!supabase) throw new Error("Supabase not initialised");
  const { error } = await supabase.rpc("ams_enqueue_upgrade", {
    queue_name: "upgrade_jobs",
    payload: job
  });
  if (error) throw error;
}
async function ensureIdempotency(key, payloadHashSource) {
  if (!supabase) return;
  if (!key) return;
  const checksum = await sha256(payloadHashSource);
  const { data, error } = await supabase.from("request_dedup").select("checksum").eq("idempotency_key", key).maybeSingle();
  if (error && error.code !== "PGRST116") {
    throw error;
  }
  if (data) {
    if (data.checksum !== checksum) {
      throw new IdempotencyError("Idempotency key re-used with different payload");
    }
    throw new IdempotencyError("Duplicate request");
  }
  const { error: insertError } = await supabase.from("request_dedup").insert({
    idempotency_key: key,
    checksum
  });
  if (insertError) throw insertError;
}
class IdempotencyError extends Error {
  constructor(message){
    super(message);
    this.name = "IdempotencyError";
  }
}
async function sha256(content) {
  const data = new TextEncoder().encode(content);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer)).map((b)=>b.toString(16).padStart(2, "0")).join("");
}
