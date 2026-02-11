'use client';

import { ValidationReport } from '@/lib/api';
import styles from './CoverageReport.module.css';

interface CoverageReportProps {
    validation: ValidationReport;
}

export default function CoverageReport({ validation }: CoverageReportProps) {
    const { summary, coverage_improvement, new_tests, already_covered, duplicates } = validation;
    const improvementPct = Math.round(coverage_improvement * 100);

    return (
        <div className={styles.container}>
            <h3 className={styles.title}>📊 Coverage Report</h3>

            {/* Stats Cards */}
            <div className={styles.stats}>
                <div className={styles.stat}>
                    <span className={styles.statValue} style={{ color: 'var(--accent-primary)' }}>
                        {summary.new}
                    </span>
                    <span className={styles.statLabel}>New Tests</span>
                </div>
                <div className={styles.stat}>
                    <span className={styles.statValue} style={{ color: 'var(--accent-success)' }}>
                        {summary.existing}
                    </span>
                    <span className={styles.statLabel}>Existing</span>
                </div>
                <div className={styles.stat}>
                    <span className={styles.statValue} style={{ color: 'var(--accent-secondary)' }}>
                        {summary.total_after_generation}
                    </span>
                    <span className={styles.statLabel}>Total After</span>
                </div>
                <div className={styles.stat}>
                    <span className={styles.statValue} style={{ color: 'var(--accent-purple)' }}>
                        {improvementPct}%
                    </span>
                    <span className={styles.statLabel}>Improvement</span>
                </div>
            </div>

            {/* Progress Bar */}
            <div className={styles.progressSection}>
                <div className={styles.progressHeader}>
                    <span>Coverage Improvement</span>
                    <span className={styles.progressPct}>{improvementPct}%</span>
                </div>
                <div className={styles.progressTrack}>
                    <div
                        className={styles.progressBar}
                        style={{ width: `${improvementPct}%` }}
                    />
                </div>
            </div>

            {/* Test Lists */}
            <div className={styles.lists}>
                {new_tests.length > 0 && (
                    <div className={styles.list}>
                        <h4 className={styles.listTitle}>
                            <span className="badge badge-blue">NEW</span>
                            {new_tests.length} new tests to generate
                        </h4>
                        <div className={styles.listItems}>
                            {new_tests.map((t) => (
                                <div key={t} className={styles.listItem}>
                                    <span className={styles.itemDot} style={{ background: 'var(--accent-primary)' }} />
                                    <code>{t}</code>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {already_covered.length > 0 && (
                    <div className={styles.list}>
                        <h4 className={styles.listTitle}>
                            <span className="badge badge-green">COVERED</span>
                            {already_covered.length} already exist
                        </h4>
                        <div className={styles.listItems}>
                            {already_covered.map((t) => (
                                <div key={t} className={styles.listItem}>
                                    <span className={styles.itemDot} style={{ background: 'var(--accent-success)' }} />
                                    <code>{t}</code>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {duplicates.length > 0 && (
                    <div className={styles.list}>
                        <h4 className={styles.listTitle}>
                            <span className="badge badge-yellow">DUPES</span>
                            {duplicates.length} duplicates found
                        </h4>
                        <div className={styles.listItems}>
                            {duplicates.map((t) => (
                                <div key={t} className={styles.listItem}>
                                    <span className={styles.itemDot} style={{ background: 'var(--accent-warning)' }} />
                                    <code>{t}</code>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
