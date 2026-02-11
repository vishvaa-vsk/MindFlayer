'use client';

import { useState, useEffect } from 'react';
import styles from './settings.module.css';
import { getSettings, updateSettings, healthCheck, AppSettings } from '@/lib/api';

export default function SettingsPage() {
    const [settings, setSettings] = useState<AppSettings | null>(null);
    const [apiKey, setApiKey] = useState('');
    const [parsingModel, setParsingModel] = useState('');
    const [generationModel, setGenerationModel] = useState('');
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking');

    useEffect(() => {
        loadSettings();
        checkHealth();
    }, []);

    const loadSettings = async () => {
        try {
            const s = await getSettings();
            setSettings(s);
            setParsingModel(s.parsing_model);
            setGenerationModel(s.generation_model);
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

    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        setError(null);
        try {
            const updates: Record<string, string> = {};
            if (apiKey) updates.openrouter_api_key = apiKey;
            if (parsingModel !== settings?.parsing_model) updates.parsing_model = parsingModel;
            if (generationModel !== settings?.generation_model) updates.generation_model = generationModel;

            if (Object.keys(updates).length === 0) {
                setError('No changes to save');
                setSaving(false);
                return;
            }

            const updated = await updateSettings(updates);
            setSettings(updated);
            setApiKey('');
            setSaved(true);
            setTimeout(() => setSaved(false), 3000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className={styles.page}>
            <div className={styles.container}>
                <h1 className={styles.title}>Settings</h1>
                <p className={styles.subtitle}>Configure your MindFlayer instance</p>

                {/* Backend Status */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}>🔌 Backend Status</h2>
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
                                API Key: {settings.has_api_key ? 'Configured ✓' : 'Not Set ✗'}
                            </span>
                        </div>
                    )}
                </div>

                {/* API Key */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}>🔑 OpenRouter API Key</h2>
                    <p className={styles.cardDesc}>
                        Get your API key from{' '}
                        <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer">
                            openrouter.ai/keys
                        </a>
                        . This key is stored in server memory only.
                    </p>
                    <input
                        type="password"
                        className="input"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder={settings?.has_api_key ? '••••••••••• (already set, enter new to change)' : 'sk-or-v1-...'}
                    />
                </div>

                {/* Models */}
                <div className={`glass-card ${styles.card}`}>
                    <h2 className={styles.cardTitle}>🤖 AI Models</h2>

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
                        <p className={styles.fieldHint}>Used for generating intelligent pytest code (pick a strong code model)</p>
                        <input
                            className="input"
                            value={generationModel}
                            onChange={(e) => setGenerationModel(e.target.value)}
                            placeholder="deepseek/deepseek-chat-v3-0324:free"
                        />
                    </div>

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
                </div>

                {/* Save */}
                <div className={styles.actions}>
                    {error && <div className={styles.error}>{error}</div>}
                    {saved && <div className={styles.success}>✓ Settings saved successfully!</div>}
                    <button
                        className="btn btn-primary btn-lg"
                        onClick={handleSave}
                        disabled={saving}
                        style={{ width: '100%' }}
                    >
                        {saving ? 'Saving...' : '💾 Save Settings'}
                    </button>
                </div>
            </div>
        </div>
    );
}
