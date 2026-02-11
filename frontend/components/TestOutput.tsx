'use client';

import { useState } from 'react';
import styles from './TestOutput.module.css';

interface TestOutputProps {
    code: string;
    testCount: number;
}

export default function TestOutput({ code, testCount }: TestOutputProps) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    // Simple syntax highlighting for Python
    const highlightCode = (raw: string): string => {
        return raw
            // Strings
            .replace(/("""[\s\S]*?"""|'''[\s\S]*?'''|"[^"]*"|'[^']*')/g, '<span class="str">$1</span>')
            // Comments
            .replace(/(#.*$)/gm, '<span class="cmt">$1</span>')
            // Keywords
            .replace(/\b(def|class|import|from|return|assert|if|else|elif|for|in|not|and|or|is|None|True|False|async|await|with|as|try|except|raise|yield|lambda|pass)\b/g, '<span class="kw">$1</span>')
            // Decorators
            .replace(/(@\w+)/g, '<span class="dec">$1</span>')
            // Functions
            .replace(/\b(test_\w+|client|response|payload|json|pytest)\b/g, '<span class="fn">$1</span>')
            // Numbers
            .replace(/\b(\d+\.?\d*)\b/g, '<span class="num">$1</span>');
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
                    <span className={styles.filename}>test_generated.py</span>
                    <span className="badge badge-blue">{testCount} tests</span>
                </div>
                <button className={styles.copyBtn} onClick={handleCopy}>
                    {copied ? '✓ Copied!' : '📋 Copy'}
                </button>
            </div>
            <div className={styles.codeWrap}>
                <pre className={styles.lineNumbers}>
                    {code.split('\n').map((_, i) => (
                        <span key={i}>{i + 1}</span>
                    ))}
                </pre>
                <pre
                    className={styles.code}
                    dangerouslySetInnerHTML={{ __html: highlightCode(code.replace(/</g, '&lt;').replace(/>/g, '&gt;')) }}
                />
            </div>
        </div>
    );
}
