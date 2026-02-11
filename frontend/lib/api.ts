/**
 * MindFlayer API Client — handles all backend communication including SSE streaming.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

// ── Types ────────────────────────────────────────────────

export interface Endpoint {
    name: string;
    method: string;
    url_path: string;
    requires_auth: boolean;
    depends_on: string[];
}

export interface AuthRule {
    scope: string;
    required_for: string[];
}

export interface SystemContext {
    endpoints: Endpoint[];
    auth_rules: AuthRule[];
    dependencies: Record<string, string[]>;
}

export interface TestScenario {
    test_name: string;
    endpoint: string;
    description: string;
    test_type: string;
}

export interface TestPlan {
    scenarios: TestScenario[];
    rationale: string;
}

export interface ValidationReport {
    total_planned: number;
    already_covered: string[];
    new_tests: string[];
    duplicates: string[];
    coverage_improvement: number;
    summary: {
        new: number;
        existing: number;
        total_after_generation: number;
    };
}

export interface GenerateTestsResult {
    context: SystemContext;
    test_plan: TestPlan;
    generated_code: string;
    outputs: Record<string, string>;
    validation: ValidationReport;
    parsed_with_llm: boolean;
}

export interface AppSettings {
    has_api_key: boolean;
    parsing_model: string;
    generation_model: string;
    llm_provider: string;
    allow_external_calls: boolean;
    app_name: string;
    app_version: string;
}

export interface OutputFormat {
    name: string;
    description: string;
    icon: string;
    language: string;
    extension: string;
}

export interface ProviderInfo {
    name: string;
    is_local: boolean;
    available: boolean;
    blocked_by_privacy: boolean;
    models: string[];
}

export interface ProvidersResponse {
    current_provider: string;
    allow_external_calls: boolean;
    providers: ProviderInfo[];
}

export interface StreamEvent {
    event: string;
    data: {
        stage: string;
        message: string;
        data?: Record<string, unknown>;
        error?: string;
    };
}

// ── Pipeline Stage ───────────────────────────────────────

export type PipelineStage = 'idle' | 'parsing' | 'planning' | 'generating' | 'validating' | 'complete' | 'error';

// ── API Calls ────────────────────────────────────────────

export async function generateTests(
    requirementsText: string,
    existingTestNames: string[] = [],
    outputFormats: string[] = ['pytest'],
): Promise<GenerateTestsResult> {
    const res = await fetch(`${API_BASE}/generate-tests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            requirements_text: requirementsText,
            existing_test_names: existingTestNames,
            output_formats: outputFormats,
        }),
    });

    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Generation failed');
    }

    return res.json();
}

export async function generateTestsStream(
    requirementsText: string,
    existingTestNames: string[] = [],
    onEvent: (event: StreamEvent) => void,
    outputFormats: string[] = ['pytest'],
): Promise<void> {
    const res = await fetch(`${API_BASE}/generate-tests-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            requirements_text: requirementsText,
            existing_test_names: existingTestNames,
            output_formats: outputFormats,
        }),
    });

    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Stream failed');
    }

    const reader = res.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        for (const line of lines) {
            if (line.startsWith('event: ')) {
                currentEvent = line.slice(7).trim();
            } else if (line.startsWith('data: ') && currentEvent) {
                try {
                    const data = JSON.parse(line.slice(6));
                    onEvent({ event: currentEvent, data });
                } catch { /* skip malformed */ }
                currentEvent = '';
            }
        }
    }
}

export async function getSettings(): Promise<AppSettings> {
    const res = await fetch(`${API_BASE}/settings`);
    if (!res.ok) throw new Error('Failed to fetch settings');
    return res.json();
}

export async function updateSettings(settings: {
    openrouter_api_key?: string;
    azure_api_key?: string;
    azure_endpoint?: string;
    azure_api_version?: string;
    azure_deployment_parsing?: string;
    azure_deployment_generation?: string;
    parsing_model?: string;
    generation_model?: string;
    llm_provider?: string;
    allow_external_calls?: boolean;
    ollama_base_url?: string;
    vllm_base_url?: string;
    tgi_base_url?: string;
}): Promise<AppSettings> {
    const res = await fetch(`${API_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || 'Failed to update settings');
    }
    return res.json();
}

export async function healthCheck(): Promise<Record<string, unknown>> {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) throw new Error('Backend unreachable');
    return res.json();
}

export async function getFormats(): Promise<Record<string, OutputFormat>> {
    const res = await fetch(`${API_BASE}/formats`);
    if (!res.ok) throw new Error('Failed to fetch formats');
    const data = await res.json();
    return data.formats;
}

export async function getProviders(): Promise<ProvidersResponse> {
    const res = await fetch(`${API_BASE}/providers`);
    if (!res.ok) throw new Error('Failed to fetch providers');
    return res.json();
}
