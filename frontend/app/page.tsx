'use client';

import Link from 'next/link';
import styles from './page.module.css';

export default function Home() {
  return (
    <div className={styles.page}>
      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroGlow} />
        <div className={styles.heroContent}>
          <div className={styles.heroBadge}>
            <span className={styles.heroBadgeDot} />
            AI-Powered Test Intelligence
          </div>
          <h1 className={styles.heroTitle}>
            Stop writing tests.
            <br />
            <span className={styles.heroGradient}>Start generating them.</span>
          </h1>
          <p className={styles.heroDesc}>
            MindFlayer analyzes your API requirements, plans comprehensive test scenarios,
            and generates executable pytest code — all powered by AI.
          </p>
          <div className={styles.heroCtas}>
            <Link href="/generate" className="btn btn-primary btn-lg">
              Generate Tests →
            </Link>
            <Link href="/settings" className="btn btn-secondary btn-lg">
              Configure API Key
            </Link>
          </div>
        </div>
      </section>

      {/* Pipeline Section */}
      <section className={styles.pipeline}>
        <h2 className={styles.sectionTitle}>How It Works</h2>
        <p className={styles.sectionDesc}>Four intelligent stages, one seamless pipeline</p>
        <div className={styles.steps}>
          {[
            { icon: '📝', title: 'Parse', desc: 'Feed in requirements — prose or structured. AI extracts endpoints, auth rules, and dependencies.', color: '#3b82f6' },
            { icon: '🧠', title: 'Plan', desc: 'Smart planner generates test scenarios: positive paths, auth failures, dependency checks, edge cases.', color: '#8b5cf6' },
            { icon: '⚡', title: 'Generate', desc: 'DeepSeek V3 writes realistic, runnable pytest code with intelligent payloads and assertions.', color: '#06b6d4' },
            { icon: '✅', title: 'Validate', desc: 'Coverage analyzer identifies gaps, deduplicates tests, and reports improvement metrics.', color: '#10b981' },
          ].map((step, i) => (
            <div key={i} className={styles.step} style={{ animationDelay: `${i * 100}ms` }}>
              <div className={styles.stepIcon} style={{ background: `${step.color}15`, color: step.color }}>
                {step.icon}
              </div>
              <div className={styles.stepConnector}>
                <div className={styles.stepLine} style={{ background: step.color }} />
              </div>
              <h3 className={styles.stepTitle}>{step.title}</h3>
              <p className={styles.stepDesc}>{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Features Grid */}
      <section className={styles.features}>
        <h2 className={styles.sectionTitle}>Built for Developers</h2>
        <div className={styles.featureGrid}>
          {[
            { icon: '🔗', title: 'OpenRouter Integration', desc: 'Access top AI models through OpenRouter — DeepSeek, Gemini, and more.' },
            { icon: '📡', title: 'Real-Time Streaming', desc: 'Watch tests generate in real-time with Server-Sent Events pipeline visualization.' },
            { icon: '🎯', title: 'Smart Test Planning', desc: 'Automatic positive, negative, auth, dependency, and edge case test detection.' },
            { icon: '📊', title: 'Coverage Analysis', desc: 'Gap detection and deduplication against your existing test suite.' },
            { icon: '🔐', title: 'Auth-Aware', desc: 'Understands authentication scopes and generates proper auth/no-auth test pairs.' },
            { icon: '🧩', title: 'Dependency Mapping', desc: 'Detects endpoint dependencies and creates failure scenario tests.' },
          ].map((feat, i) => (
            <div key={i} className={`glass-card ${styles.featureCard}`} style={{ animationDelay: `${i * 80}ms` }}>
              <div className={styles.featureIcon}>{feat.icon}</div>
              <h3 className={styles.featureTitle}>{feat.title}</h3>
              <p className={styles.featureDesc}>{feat.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Section */}
      <section className={styles.cta}>
        <div className={styles.ctaGlow} />
        <h2 className={styles.ctaTitle}>Ready to supercharge your testing?</h2>
        <p className={styles.ctaDesc}>
          Paste your API requirements and get a complete test suite in seconds.
        </p>
        <Link href="/generate" className="btn btn-primary btn-lg">
          Launch MindFlayer →
        </Link>
      </section>
    </div>
  );
}
