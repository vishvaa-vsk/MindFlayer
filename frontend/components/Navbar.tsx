'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import styles from './Navbar.module.css';

export default function Navbar() {
    const pathname = usePathname();
    const [scrolled, setScrolled] = useState(false);

    useEffect(() => {
        const onScroll = () => setScrolled(window.scrollY > 10);
        window.addEventListener('scroll', onScroll);
        return () => window.removeEventListener('scroll', onScroll);
    }, []);

    return (
        <nav className={`${styles.nav} ${scrolled ? styles.scrolled : ''}`}>
            <div className={styles.inner}>
                <Link href="/" className={styles.logo}>
                    <span className={styles.logoIcon}>🧠</span>
                    <span className={styles.logoText}>MindFlayer</span>
                </Link>

                <div className={styles.links}>
                    <Link
                        href="/"
                        className={`${styles.link} ${pathname === '/' ? styles.active : ''}`}
                    >
                        Home
                    </Link>
                    <Link
                        href="/generate"
                        className={`${styles.link} ${pathname === '/generate' ? styles.active : ''}`}
                    >
                        Generate
                    </Link>
                    <Link
                        href="/settings"
                        className={`${styles.link} ${pathname === '/settings' ? styles.active : ''}`}
                    >
                        Settings
                    </Link>
                </div>

                <Link href="/generate" className={`btn btn-primary ${styles.cta}`}>
                    Generate Tests →
                </Link>
            </div>
        </nav>
    );
}
