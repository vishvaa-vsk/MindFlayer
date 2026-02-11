'use client';

import { useState, useCallback, useEffect } from 'react';
import styles from './generate.module.css';
import PipelineVisualizer from '@/components/PipelineVisualizer';
import TestOutput from '@/components/TestOutput';
import CoverageReport from '@/components/CoverageReport';
import {
    generateTestsStream,
    getFormats,
    PipelineStage,
    GenerateTestsResult,
    StreamEvent,
    OutputFormat,
} from '@/lib/api';

const EXAMPLE_STRUCTURED = `POST /users (requires admin_auth)
GET /users/:id (requires user_auth)
PUT /users/:id (requires user_auth, depends on POST /users)
DELETE /users/:id (requires admin_auth)
POST /orders (requires user_auth, depends on POST /users)
GET /orders/:id (requires user_auth, depends on POST /orders)
GET /orders (requires user_auth)`;

const EXAMPLE_PROSE = `The system allows users to register and login. 
Authenticated users can create orders with products, 
view their order history, and cancel pending orders. 
Admin users can manage products and view all orders. 
Payment processing requires a valid order.`;

const FORMAT_ICONS: Record<string, string> = {
    pytest: '🐍',
    postman: '📮',
    junit: '🧪',
    gherkin: '🥒',
    openapi: '📋',
};

const FORMAT_LANGUAGES: Record<string, string> = {
    pytest: 'python',
    postman: 'json',
    junit: 'xml',
    gherkin: 'gherkin',
    openapi: 'yaml',
};

export default function GeneratePage() {
    const [input, setInput] = useState('');
    const [existingTests, setExistingTests] = useState('');
    const [stage, setStage] = useState<PipelineStage>('idle');
    const [stageMessages, setStageMessages] = useState<Record<string, string>>({});
    const [result, setResult] = useState<GenerateTestsResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<string>('pytest');

    // Output formats
    const [availableFormats, setAvailableFormats] = useState<Record<string, OutputFormat>>({});
    const [selectedFormats, setSelectedFormats] = useState<string[]>(['pytest']);

    useEffect(() => {
        loadFormats();
    }, []);

    const loadFormats = async () => {
        try {
            const formats = await getFormats();
            setAvailableFormats(formats);
        } catch {
            // Default formats if backend unavailable
            setAvailableFormats({
                pytest: { name: 'Pytest', description: 'Python pytest suite', icon: '🐍', language: 'python', extension: '.py' },
                postman: { name: 'Postman', description: 'Postman Collection', icon: '📮', language: 'json', extension: '.json' },
                junit: { name: 'JUnit XML', description: 'JUnit XML report', icon: '🧪', language: 'xml', extension: '.xml' },
                gherkin: { name: 'Gherkin', description: 'BDD feature file', icon: '🥒', language: 'gherkin', extension: '.feature' },
                openapi: { name: 'OpenAPI', description: 'OpenAPI 3.0 spec', icon: '📋', language: 'yaml', extension: '.yaml' },
            });
        }
    };

    const toggleFormat = (fmt: string) => {
        setSelectedFormats((prev) => {
            if (prev.includes(fmt)) {
                // Don't allow deselecting all
                if (prev.length === 1) return prev;
                return prev.filter((f) => f !== fmt);
            }
            return [...prev, fmt];
        });
    };

    const handleGenerate = useCallback(async () => {
        if (!input.trim()) return;

        setStage('parsing');
        setStageMessages({});
        setResult(null);
        setError(null);
        setActiveTab(selectedFormats[0] || 'pytest');

        const existingList = existingTests
            .split('\n')
            .map((t) => t.trim())
            .filter(Boolean);

        try {
            await generateTestsStream(input, existingList, (event: StreamEvent) => {
                const { data } = event;

                setStageMessages((prev) => ({
                    ...prev,
                    [data.stage]: data.message,
                }));

                switch (event.event) {
                    case 'stage':
                        setStage(data.stage as PipelineStage);
                        break;
                    case 'complete':
                        setStage('complete');
                        if (data.data) {
                            setResult(data.data as unknown as GenerateTestsResult);
                        }
                        break;
                    case 'error':
                        setStage('error');
                        setError(data.message || 'Unknown error');
                        break;
                }
            }, selectedFormats);
        } catch (err) {
            setStage('error');
            setError(err instanceof Error ? err.message : 'Connection failed — is the backend running?');
        }
    }, [input, existingTests, selectedFormats]);

    const loadExample = (type: 'structured' | 'prose') => {
        setInput(type === 'structured' ? EXAMPLE_STRUCTURED : EXAMPLE_PROSE);
        setResult(null);
        setStage('idle');
        setError(null);
    };

    const isRunning = stage !== 'idle' && stage !== 'complete' && stage !== 'error';

    // Get output tabs from result
    const outputTabs = result?.outputs ? Object.keys(result.outputs) : [];

    return (
        <div className={styles.page}>
            <div className={styles.container}>
                {/* Header */}
                <div className={styles.header}>
                    <h1 className={styles.title}>Generate Tests</h1>
                    <p className={styles.subtitle}>
                        Paste your API requirements below — structured or natural language. MindFlayer will analyze, plan, and generate tests in multiple formats.
                    </p>
                </div>

                {/* Input Section */}
                <div className={styles.inputSection}>
                    <div className={styles.inputHeader}>
                        <label className={styles.inputLabel}>API Requirements</label>
                        <div className={styles.examples}>
                            <button className="btn btn-ghost" onClick={() => loadExample('structured')}>
                                📝 Structured Example
                            </button>
                            <button className="btn btn-ghost" onClick={() => loadExample('prose')}>
                                💬 Prose Example
                            </button>
                        </div>
                    </div>
                    <textarea
                        className="input"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder={`Enter API requirements...\n\nStructured format:\nPOST /orders (requires user_auth)\nGET /orders/:id (requires user_auth, depends on POST /orders)\n\nOr natural language:\n"Users can register, login, and create orders..."`}
                        rows={10}
                        disabled={isRunning}
                    />

                    {/* Existing Tests (collapsible) */}
                    <details className={styles.existingTests}>
                        <summary className={styles.existingTestsSummary}>
                            ➕ Existing test names (optional — for deduplication)
                        </summary>
                        <textarea
                            className="input"
                            value={existingTests}
                            onChange={(e) => setExistingTests(e.target.value)}
                            placeholder="One test name per line (e.g. test_create_order_positive)"
                            rows={4}
                            disabled={isRunning}
                            style={{ marginTop: '8px' }}
                        />
                    </details>

                    {/* Output Format Selector */}
                    <div className={styles.formatSelector}>
                        <label className={styles.formatLabel}>Output Formats</label>
                        <div className={styles.formatGrid}>
                            {Object.entries(availableFormats).map(([key, format]) => (
                                <button
                                    key={key}
                                    className={`${styles.formatChip} ${selectedFormats.includes(key) ? styles.formatChipActive : ''}`}
                                    onClick={() => toggleFormat(key)}
                                    disabled={isRunning}
                                    title={format.description}
                                >
                                    <span className={styles.formatIcon}>{FORMAT_ICONS[key] || '📄'}</span>
                                    <span>{format.name}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    <button
                        className={`btn btn-primary btn-lg ${styles.generateBtn}`}
                        onClick={handleGenerate}
                        disabled={isRunning || !input.trim()}
                    >
                        {isRunning ? (
                            <>
                                <span className="spinner" /> Generating...
                            </>
                        ) : (
                            `🧠 Generate in ${selectedFormats.length} format${selectedFormats.length > 1 ? 's' : ''}`
                        )}
                    </button>
                </div>

                {/* Pipeline Visualizer */}
                <PipelineVisualizer currentStage={stage} stageMessages={stageMessages} />

                {/* Error Display */}
                {error && (
                    <div className={styles.error}>
                        <strong>Error:</strong> {error}
                    </div>
                )}

                {/* Results */}
                {result && (
                    <div className={styles.results}>
                        {/* Tabs */}
                        <div className={styles.tabs}>
                            {outputTabs.map((fmt) => (
                                <button
                                    key={fmt}
                                    className={`${styles.tab} ${activeTab === fmt ? styles.tabActive : ''}`}
                                    onClick={() => setActiveTab(fmt)}
                                >
                                    {FORMAT_ICONS[fmt] || '📄'} {availableFormats[fmt]?.name || fmt}
                                </button>
                            ))}
                            <button
                                className={`${styles.tab} ${activeTab === 'coverage' ? styles.tabActive : ''}`}
                                onClick={() => setActiveTab('coverage')}
                            >
                                📊 Coverage
                            </button>
                            <button
                                className={`${styles.tab} ${activeTab === 'plan' ? styles.tabActive : ''}`}
                                onClick={() => setActiveTab('plan')}
                            >
                                🧠 Plan
                            </button>
                        </div>

                        {/* Tab Content */}
                        <div className={styles.tabContent}>
                            {/* Output format tabs */}
                            {outputTabs.includes(activeTab) && result.outputs[activeTab] && (
                                <TestOutput
                                    code={result.outputs[activeTab]}
                                    testCount={result.test_plan.scenarios.length}
                                    language={FORMAT_LANGUAGES[activeTab] || 'text'}
                                    filename={`tests${availableFormats[activeTab]?.extension || '.txt'}`}
                                />
                            )}

                            {activeTab === 'coverage' && (
                                <CoverageReport validation={result.validation} />
                            )}

                            {activeTab === 'plan' && (
                                <div className={styles.planView}>
                                    <div className={styles.planRationale}>
                                        <strong>Rationale:</strong> {result.test_plan.rationale}
                                    </div>
                                    <div className={styles.scenarioGrid}>
                                        {result.test_plan.scenarios.map((scenario) => (
                                            <div key={scenario.test_name} className={`glass-card ${styles.scenarioCard}`}>
                                                <div className={styles.scenarioHeader}>
                                                    <code className={styles.scenarioName}>{scenario.test_name}</code>
                                                    <span className={`badge ${scenario.test_type === 'positive' ? 'badge-green' :
                                                        scenario.test_type === 'no_auth' ? 'badge-red' :
                                                            scenario.test_type === 'dependency_failure' ? 'badge-yellow' :
                                                                'badge-purple'
                                                        }`}>
                                                        {scenario.test_type}
                                                    </span>
                                                </div>
                                                <p className={styles.scenarioDesc}>{scenario.description}</p>
                                                <div className={styles.scenarioEndpoint}>
                                                    <span className="badge badge-blue">{scenario.endpoint}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Context Info */}
                        {result.parsed_with_llm && (
                            <div className={styles.llmBadge}>
                                🤖 Requirements were parsed using AI (natural language detected)
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
