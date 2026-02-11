'use client';

import { useState } from 'react';
import styles from './TestOutput.module.css';

interface TestOutputProps {
    code: string;
    testCount: number;
    language?: string;
    filename?: string;
}

export default function TestOutput({ code, testCount, language = 'python', filename }: TestOutputProps) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const handleDownload = () => {
        const blob = new Blob([code], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = displayFilename;
        a.click();
        URL.revokeObjectURL(url);
    };

    // Determine display filename
    const displayFilename = filename || getDefaultFilename(language);

    // Language-aware syntax highlighting
    const highlightCode = (raw: string): string => {
        const escaped = raw.replace(/</g, '&lt;').replace(/>/g, '&gt;');

        switch (language) {
            case 'python':
                return highlightPython(escaped);
            case 'json':
                return highlightJson(escaped);
            case 'xml':
                return highlightXml(escaped);
            case 'yaml':
                return highlightYaml(escaped);
            case 'gherkin':
                return highlightGherkin(escaped);
            default:
                return escaped;
        }
    };

    if (!code) return null;

    return (
        <div className={styles.container}>
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <div className={styles.dots}>
                        <span className={styles.dot} style={{ background: '#ef4444' }} />
                        <span className={styles.dot} style={{ background: '#f59e0b' }} />
                        <span className={styles.dot} style={{ background: '#10b981' }} />
                    </div>
                    <span className={styles.filename}>{displayFilename}</span>
                    <span className="badge badge-blue">{testCount} tests</span>
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                    <button className={styles.copyBtn} onClick={handleDownload}>
                        ⬇ Download
                    </button>
                    <button className={styles.copyBtn} onClick={handleCopy}>
                        {copied ? '✓ Copied!' : '📋 Copy'}
                    </button>
                </div>
            </div>
            <div className={styles.codeWrap}>
                <pre className={styles.lineNumbers}>
                    {code.split('\n').map((_, i) => (
                        <span key={i}>{i + 1}</span>
                    ))}
                </pre>
                <pre
                    className={styles.code}
                    dangerouslySetInnerHTML={{ __html: highlightCode(code) }}
                />
            </div>
        </div>
    );
}

function getDefaultFilename(language: string): string {
    const map: Record<string, string> = {
        python: 'test_generated.py',
        json: 'collection.json',
        xml: 'report.xml',
        yaml: 'openapi.yaml',
        gherkin: 'tests.feature',
    };
    return map[language] || 'output.txt';
}

function highlightPython(code: string): string {
    return code
        .replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"[^"]*"|'[^']*')/g, '<span class="str">$1</span>')
        .replace(/(#.*$)/gm, '<span class="cmt">$1</span>')
        .replace(/\b(def|class|import|from|return|assert|if|else|elif|for|in|not|and|or|is|None|True|False|async|await|with|as|try|except|raise|yield|lambda|pass)\b/g, '<span class="kw">$1</span>')
        .replace(/(@\w+)/g, '<span class="dec">$1</span>')
        .replace(/\b(test_\w+|client|response|payload|json|pytest)\b/g, '<span class="fn">$1</span>')
        .replace(/\b(\d+\.?\d*)\b/g, '<span class="num">$1</span>');
}

function highlightJson(code: string): string {
    return code
        .replace(/("(?:[^"\\]|\\.)*")\s*:/g, '<span class="kw">$1</span>:')
        .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="str">$1</span>')
        .replace(/:\s*(\d+\.?\d*)/g, ': <span class="num">$1</span>')
        .replace(/:\s*(true|false|null)\b/g, ': <span class="kw">$1</span>');
}

function highlightXml(code: string): string {
    return code
        .replace(/(&lt;\/?)([\w:-]+)/g, '$1<span class="kw">$2</span>')
        .replace(/([\w:-]+)=("(?:[^"\\]|\\.)*")/g, '<span class="fn">$1</span>=<span class="str">$2</span>')
        .replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="cmt">$1</span>');
}

function highlightYaml(code: string): string {
    return code
        .replace(/(#.*$)/gm, '<span class="cmt">$1</span>')
        .replace(/^(\s*)([\w-]+):/gm, '$1<span class="kw">$2</span>:')
        .replace(/:\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, ': <span class="str">$1</span>')
        .replace(/:\s*(\d+\.?\d*)\s*$/gm, ': <span class="num">$1</span>')
        .replace(/:\s*(true|false|null)\s*$/gm, ': <span class="kw">$1</span>');
}

function highlightGherkin(code: string): string {
    return code
        .replace(/(#.*$)/gm, '<span class="cmt">$1</span>')
        .replace(/^(\s*)(Feature|Background|Scenario|Scenario Outline|Examples|Given|When|Then|And|But)(:|\b)/gm, '$1<span class="kw">$2</span>$3')
        .replace(/(@\w+)/g, '<span class="dec">$1</span>')
        .replace(/("(?:[^"\\]|\\.)*")/g, '<span class="str">$1</span>');
}
