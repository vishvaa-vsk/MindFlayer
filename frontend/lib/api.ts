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
    validation: ValidationReport;
    parsed_with_llm: boolean;
}

export interface AppSettings {
    has_api_key: boolean;
    parsing_model: string;
    generation_model: string;
    app_name: string;
    app_version: string;
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
): Promise<GenerateTestsResult> {
    const res = await fetch(`${API_BASE}/generate-tests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            requirements_text: requirementsText,
            existing_test_names: existingTestNames,
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
): Promise<void> {
    const res = await fetch(`${API_BASE}/generate-tests-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            requirements_text: requirementsText,
            existing_test_names: existingTestNames,
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
    parsing_model?: string;
    generation_model?: string;
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
