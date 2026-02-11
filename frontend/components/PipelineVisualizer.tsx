'use client';

import { PipelineStage } from '@/lib/api';
import styles from './PipelineVisualizer.module.css';

interface PipelineVisualizerProps {
    currentStage: PipelineStage;
    stageMessages: Record<string, string>;
}

const STAGES: { key: PipelineStage; label: string; icon: string }[] = [
    { key: 'parsing', label: 'Parse', icon: '📝' },
    { key: 'planning', label: 'Plan', icon: '🧠' },
    { key: 'generating', label: 'Generate', icon: '⚡' },
    { key: 'validating', label: 'Validate', icon: '✅' },
];

export default function PipelineVisualizer({ currentStage, stageMessages }: PipelineVisualizerProps) {
    const getStageStatus = (stageKey: PipelineStage): 'pending' | 'active' | 'done' => {
        if (currentStage === 'idle' || currentStage === 'error') return 'pending';
        if (currentStage === 'complete') return 'done';

        const stageOrder = ['parsing', 'planning', 'generating', 'validating'];
        const currentIndex = stageOrder.indexOf(currentStage);
        const stageIndex = stageOrder.indexOf(stageKey);

        if (stageIndex < currentIndex) return 'done';
        if (stageIndex === currentIndex) return 'active';
        return 'pending';
    };

    if (currentStage === 'idle') return null;

    return (
        <div className={styles.pipeline}>
            <div className={styles.stages}>
                {STAGES.map((stage, i) => {
                    const status = getStageStatus(stage.key);
                    return (
                        <div key={stage.key} className={styles.stageWrapper}>
                            {i > 0 && (
                                <div className={`${styles.connector} ${status !== 'pending' ? styles.connectorActive : ''}`} />
                            )}
                            <div className={`${styles.stage} ${styles[status]}`}>
                                <div className={styles.stageIcon}>
                                    {status === 'active' ? (
                                        <div className={styles.spinner} />
                                    ) : status === 'done' ? (
                                        <span className={styles.checkmark}>✓</span>
                                    ) : (
                                        <span>{stage.icon}</span>
                                    )}
                                </div>
                                <div className={styles.stageInfo}>
                                    <span className={styles.stageLabel}>{stage.label}</span>
                                    {stageMessages[stage.key] && (
                                        <span className={styles.stageMsg}>{stageMessages[stage.key]}</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
            {currentStage === 'complete' && (
                <div className={styles.completeMsg}>
                    <span>🎉</span> All stages complete!
                </div>
            )}
            {currentStage === 'error' && (
                <div className={styles.errorMsg}>
                    <span>❌</span> Pipeline failed — check the error below.
                </div>
            )}
        </div>
    );
}
