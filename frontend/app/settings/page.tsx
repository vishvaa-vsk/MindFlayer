'use client';

import { useState, useEffect } from 'react';
import { Globe, Horse, Lightning, Smiley, Cloud, Plug, LinkSimple, ShieldCheck, Robot, FloppyDisk, Lock, Warning, Check } from '@phosphor-icons/react';
import styles from './settings.module.css';
import { getSettings, updateSettings, healthCheck, getProviders, AppSettings, ProviderInfo } from '@/lib/api';

const PROVIDER_META: Record<string, { label: string; icon: any; desc: string }> = {
    openrouter: { label: 'OpenRouter', icon: Globe, desc: 'Cloud gateway — 100+ models via single API key' },
    ollama: { label: 'Ollama', icon: Horse, desc: 'Local inference — fully air-gapped, privacy-safe' },
    vllm: { label: 'vLLM', icon: Lightning, desc: 'High-throughput local serving — OpenAI-compatible' },
    tgi: { label: 'HuggingFace TGI', icon: Smiley, desc: 'HuggingFace Text Generation Inference' },
    azure: { label: 'Azure OpenAI', icon: Cloud, desc: 'Enterprise Azure-hosted GPT models' },
};

export default function SettingsPage() {
    const [settings, setSettings] = useState<AppSettings | null>(null);
    const [apiKey, setApiKey] = useState('');
    const [parsingModel, setParsingModel] = useState('');
    const [generationModel, setGenerationModel] = useState('');
    const [provider, setProvider] = useState('openrouter');
    const [allowExternal, setAllowExternal] = useState(true);

    // Azure fields
    const [azureEndpoint, setAzureEndpoint] = useState('');
    const [azureApiKey, setAzureApiKey] = useState('');
    const [azureDeployParsing, setAzureDeployParsing] = useState('');
    const [azureDeployGeneration, setAzureDeployGeneration] = useState('');

    const [providers, setProviders] = useState<ProviderInfo[]>([]);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');

    useEffect(() => {
        loadSettings();
        checkHealth();
        loadProviders();
    }, []);

    const loadSettings = async () => {
        try {
            const s = await getSettings();
            setSettings(s);
            setParsingModel(s.parsing_model);
            setGenerationModel(s.generation_model);
            setProvider(s.llm_provider);
            setAllowExternal(s.allow_external_calls);
        } catch {
            setError('Could not load settings — is the backend running?');
        }
    };

    const checkHealth = async () => {
        try {
            await healthCheck();
            setBackendStatus('online');
        } catch {
            setBackendStatus('offline');
        }
    };

    const loadProviders = async () => {
        try {
            const data = await getProviders();
            setProviders(data.providers);
        } catch { /* ignore */ }
    };

    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        setError(null);
        try {
            const updates: Record<string, unknown> = {};

            if (provider !== settings?.llm_provider) updates.llm_provider = provider;
            if (allowExternal !== settings?.allow_external_calls) updates.allow_external_calls = allowExternal;
            if (apiKey) updates.openrouter_api_key = apiKey;
            if (parsingModel !== settings?.parsing_model) updates.parsing_model = parsingModel;
            if (generationModel !== settings?.generation_model) updates.generation_model = generationModel;

            // Azure fields
            if (azureEndpoint) updates.azure_endpoint = azureEndpoint;
            if (azureApiKey) updates.azure_api_key = azureApiKey;
            if (azureDeployParsing) updates.azure_deployment_parsing = azureDeployParsing;
            if (azureDeployGeneration) updates.azure_deployment_generation = azureDeployGeneration;

            if (Object.keys(updates).length === 0) {
                setError('No changes to save');
                setSaving(false);
                return;
            }

            const updated = await updateSettings(updates as Parameters<typeof updateSettings>[0]);
            setSettings(updated);
            setApiKey('');
            setAzureApiKey('');
            setSaved(true);
            loadProviders(); // Refresh provider status
            setTimeout(() => setSaved(false), 3000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save');
        } finally {
            setSaving(false);
        }
    };

    const getProviderStatus = (name: string): ProviderInfo | undefined => {
        return providers.find((p) => p.name === name);
    };

    return (
        <div className={styles.page}>
            <div className={styles.container}>
                <h1 className={styles.title}>Settings</h1>
                <p className={styles.subtitle}>Configure your MindFlayer instance — providers, models, and security</p>

                {/* Backend Status */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}><Plug size={24} weight="duotone" /> Backend Status</h2>
                    <div className={styles.statusRow}>
                        <div className={`${styles.statusDot} ${styles[backendStatus]}`} />
                        <span>
                            {backendStatus === 'checking' && 'Checking connection...'}
                            {backendStatus === 'online' && 'Backend is online'}
                            {backendStatus === 'offline' && 'Backend is offline — start it with: cd backend && uv run uvicorn main:app --reload'}
                        </span>
                    </div>
                    {settings && (
                        <div className={styles.statusInfo}>
                            <span className="badge badge-blue">{settings.app_name} v{settings.app_version}</span>
                            <span className={`badge ${settings.has_api_key ? 'badge-green' : 'badge-red'}`}>
                                API Key: {settings.has_api_key ? 'Configured' : 'Not Set'}
                            </span>
                            <span className="badge badge-purple">
                                Provider: {PROVIDER_META[settings.llm_provider]?.label || settings.llm_provider}
                            </span>
                        </div>
                    )}
                </div>

                {/* LLM Provider Selector */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}><LinkSimple size={24} weight="duotone" /> LLM Provider</h2>
                    <p className={styles.cardDesc}>
                        Choose your LLM backend. Local providers (Ollama, vLLM, TGI) keep all data on-premise.
                    </p>
                    <div className={styles.providerGrid}>
                        {Object.entries(PROVIDER_META).map(([key, meta]) => {
                            const status = getProviderStatus(key);
                            const isSelected = provider === key;
                            const isBlocked = status?.blocked_by_privacy;

                            return (
                                <button
                                    key={key}
                                    className={`${styles.providerCard} ${isSelected ? styles.providerCardActive : ''} ${isBlocked ? styles.providerCardBlocked : ''}`}
                                    onClick={() => !isBlocked && setProvider(key)}
                                    disabled={!!isBlocked}
                                >
                                    <div className={styles.providerHeader}>
                                        <span className={styles.providerIcon}>{<meta.icon size={24} weight="duotone" />}</span>
                                        <span className={styles.providerName}>{meta.label}</span>
                                        {status && (
                                            <span className={`${styles.providerStatus} ${status.available ? styles.providerOnline : styles.providerOffline}`}>
                                                {isBlocked ? <Lock size={14} weight="duotone" /> : status.available ? '●' : '○'}
                                            </span>
                                        )}
                                    </div>
                                    <p className={styles.providerDesc}>{meta.desc}</p>
                                    {status?.is_local && (
                                        <span className={styles.localBadge}><Lock size={12} weight="duotone" /> Local</span>
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </div>

                {/* Data Privacy */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}><ShieldCheck size={24} weight="duotone" /> Data Privacy</h2>
                    <div className={styles.toggleRow}>
                        <div>
                            <label className={styles.fieldLabel}>Local-Only Mode</label>
                            <p className={styles.fieldHint}>
                                When enabled, blocks all external API calls (OpenRouter, Azure). Only local providers are allowed.
                            </p>
                        </div>
                        <button
                            className={`${styles.toggle} ${!allowExternal ? styles.toggleActive : ''}`}
                            onClick={() => setAllowExternal(!allowExternal)}
                        >
                            <span className={styles.toggleDot} />
                        </button>
                    </div>
                    {!allowExternal && (
                        <div className={styles.privacyWarning}>
                            <Warning size={18} weight="duotone" /> Local-only mode is active. Cloud providers (OpenRouter, Azure) are blocked. Use Ollama, vLLM, or TGI.
                        </div>
                    )}
                </div>

                {/* Provider-Specific Config: OpenRouter */}
                {provider === 'openrouter' && (
                    <div className={`glass-card ${styles.card}`}>
                        <h2 className={styles.cardTitle}><Globe size={24} weight="duotone" /> OpenRouter Configuration</h2>
                        <p className={styles.cardDesc}>
                            Get your API key from{' '}
                            <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer">
                                openrouter.ai/keys
                            </a>
                        </p>
                        <input
                            type="password"
                            className="input"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            placeholder={settings?.has_api_key ? '••••••••••• (already set)' : 'sk-or-v1-...'}
                        />
                    </div>
                )}

                {/* Provider-Specific Config: Azure */}
                {provider === 'azure' && (
                    <div className={`glass-card ${styles.card}`}>
                        <h2 className={styles.cardTitle}><Cloud size={24} weight="duotone" /> Azure OpenAI Configuration</h2>
                        <div className={styles.fieldGroup}>
                            <label className={styles.fieldLabel}>Azure Endpoint</label>
                            <input
                                className="input"
                                value={azureEndpoint}
                                onChange={(e) => setAzureEndpoint(e.target.value)}
                                placeholder="https://your-resource.openai.azure.com"
                            />
                        </div>
                        <div className={styles.fieldGroup}>
                            <label className={styles.fieldLabel}>Azure API Key</label>
                            <input
                                type="password"
                                className="input"
                                value={azureApiKey}
                                onChange={(e) => setAzureApiKey(e.target.value)}
                                placeholder="your-azure-api-key"
                            />
                        </div>
                        <div className={styles.fieldGroup}>
                            <label className={styles.fieldLabel}>Parsing Deployment Name</label>
                            <input
                                className="input"
                                value={azureDeployParsing}
                                onChange={(e) => setAzureDeployParsing(e.target.value)}
                                placeholder="gpt-4o-mini"
                            />
                        </div>
                        <div className={styles.fieldGroup}>
                            <label className={styles.fieldLabel}>Generation Deployment Name</label>
                            <input
                                className="input"
                                value={azureDeployGeneration}
                                onChange={(e) => setAzureDeployGeneration(e.target.value)}
                                placeholder="gpt-4o"
                            />
                        </div>
                    </div>
                )}

                {/* Models */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}><Robot size={24} weight="duotone" /> AI Models</h2>

                    <div className={styles.fieldGroup}>
                        <label className={styles.fieldLabel}>Parsing Model</label>
                        <p className={styles.fieldHint}>Used for converting natural language requirements to structured format</p>
                        <input
                            className="input"
                            value={parsingModel}
                            onChange={(e) => setParsingModel(e.target.value)}
                            placeholder="google/gemini-2.0-flash-001"
                        />
                    </div>

                    <div className={styles.fieldGroup}>
                        <label className={styles.fieldLabel}>Code Generation Model</label>
                        <p className={styles.fieldHint}>Used for generating intelligent test code (pick a strong code model)</p>
                        <input
                            className="input"
                            value={generationModel}
                            onChange={(e) => setGenerationModel(e.target.value)}
                            placeholder="deepseek/deepseek-chat-v3-0324:free"
                        />
                    </div>

                    {provider === 'openrouter' && (
                        <div className={styles.modelSuggestions}>
                            <span className={styles.suggestLabel}>Recommended free models:</span>
                            <div className={styles.suggestList}>
                                {[
                                    'deepseek/deepseek-chat-v3-0324:free',
                                    'google/gemini-2.0-flash-001',
                                    'meta-llama/llama-3.3-70b-instruct:free',
                                    'qwen/qwen-2.5-coder-32b-instruct:free',
                                ].map((m) => (
                                    <button
                                        key={m}
                                        className={styles.suggestBtn}
                                        onClick={() => setGenerationModel(m)}
                                    >
                                        {m}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Show available models from provider */}
                    {(() => {
                        const providerInfo = getProviderStatus(provider);
                        if (providerInfo?.models && providerInfo.models.length > 0 && provider !== 'openrouter') {
                            return (
                                <div className={styles.modelSuggestions}>
                                    <span className={styles.suggestLabel}>Available on {PROVIDER_META[provider]?.label}:</span>
                                    <div className={styles.suggestList}>
                                        {providerInfo.models.map((m) => (
                                            <button
                                                key={m}
                                                className={styles.suggestBtn}
                                                onClick={() => {
                                                    setParsingModel(m);
                                                    setGenerationModel(m);
                                                }}
                                            >
                                                {m}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            );
                        }
                        return null;
                    })()}
                </div>

                {/* Save */}
                <div className={styles.actions}>
                    {error && <div className={styles.error}>{error}</div>}
                    {saved && <div className={styles.success}><Check size={16} weight="bold" /> Settings saved successfully!</div>}
                    <button
                        className="btn btn-primary btn-lg"
                        onClick={handleSave}
                        disabled={saving}
                        style={{ width: '100%' }}
                    >
                        {saving ? 'Saving...' : <><FloppyDisk size={20} weight="duotone" /> Save Settings</>}
                    </button>
                </div>
            </div>
        </div>
    );
}
