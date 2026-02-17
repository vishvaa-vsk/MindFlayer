"use client";

import { Scan, Tag, Cube, CheckSquare, Gavel } from "@phosphor-icons/react";
import { CodeContext } from "@/lib/api";
import styles from "./CodeContextDisplay.module.css";

interface CodeContextDisplayProps {
  codeContext: CodeContext;
}

export default function CodeContextDisplay({
  codeContext,
}: CodeContextDisplayProps) {
  const hasContent =
    codeContext.enums.length > 0 ||
    codeContext.validators.length > 0 ||
    codeContext.business_rules.length > 0 ||
    codeContext.models.length > 0;

  if (!hasContent) {
    return null;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3 className={styles.title}>
          <Scan size={20} weight="duotone" /> Code Analysis Results
        </h3>
        <p className={styles.subtitle}>
          Extracted metadata from your source files
        </p>
      </div>

      <div className={styles.grid}>
        {/* Enums */}
        {codeContext.enums.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>
                <Tag size={18} weight="duotone" />
              </span>
              <h4 className={styles.sectionTitle}>
                Enums ({codeContext.enums.length})
              </h4>
            </div>
            <div className={styles.items}>
              {codeContext.enums.map((enumDef, idx) => (
                <div key={idx} className={styles.item}>
                  <div className={styles.itemHeader}>
                    <code className={styles.itemName}>{enumDef.name}</code>
                    {enumDef.source_file && (
                      <span className={styles.itemSource}>
                        {enumDef.source_file}
                      </span>
                    )}
                  </div>
                  {enumDef.description && (
                    <p className={styles.itemDesc}>{enumDef.description}</p>
                  )}
                  <div className={styles.enumValues}>
                    {enumDef.values.map((val, vidx) => (
                      <span key={vidx} className={styles.enumValue}>
                        {val}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Models */}
        {codeContext.models.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>
                <Cube size={18} weight="duotone" />
              </span>
              <h4 className={styles.sectionTitle}>
                Models ({codeContext.models.length})
              </h4>
            </div>
            <div className={styles.items}>
              {codeContext.models.map((model, idx) => (
                <div key={idx} className={styles.item}>
                  <div className={styles.itemHeader}>
                    <code className={styles.itemName}>{model.name}</code>
                    {model.source_file && (
                      <span className={styles.itemSource}>
                        {model.source_file}
                      </span>
                    )}
                  </div>
                  <div className={styles.fields}>
                    {Object.entries(model.fields).map(([name, type], fidx) => (
                      <div key={fidx} className={styles.field}>
                        <code className={styles.fieldName}>{name}</code>
                        <span className={styles.fieldType}>{type}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Validators */}
        {codeContext.validators.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>
                <CheckSquare size={18} weight="duotone" />
              </span>
              <h4 className={styles.sectionTitle}>
                Validators ({codeContext.validators.length})
              </h4>
            </div>
            <div className={styles.items}>
              {codeContext.validators.map((validator, idx) => (
                <div key={idx} className={styles.item}>
                  <div className={styles.validatorRow}>
                    <code className={styles.itemName}>
                      {validator.field_name}
                    </code>
                    <span className={styles.validatorType}>
                      {validator.rule_type}
                    </span>
                    {validator.constraint && (
                      <code className={styles.validatorConstraint}>
                        = {String(validator.constraint)}
                      </code>
                    )}
                  </div>
                  {validator.error_message && (
                    <p className={styles.itemDesc}>{validator.error_message}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Business Rules */}
        {codeContext.business_rules.length > 0 && (
          <div className={styles.section}>
            <div className={styles.sectionHeader}>
              <span className={styles.sectionIcon}>
                <Gavel size={18} weight="duotone" />
              </span>
              <h4 className={styles.sectionTitle}>
                Business Rules ({codeContext.business_rules.length})
              </h4>
            </div>
            <div className={styles.items}>
              {codeContext.business_rules.map((rule, idx) => (
                <div key={idx} className={styles.item}>
                  <div className={styles.itemHeader}>
                    <span className={styles.ruleDesc}>{rule.description}</span>
                    {rule.applies_to && (
                      <span className={styles.itemSource}>
                        {rule.applies_to}
                      </span>
                    )}
                  </div>
                  <code className={styles.ruleCondition}>
                    if {rule.condition}
                  </code>
                  {rule.error_message && (
                    <p className={styles.ruleError}>→ {rule.error_message}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={styles.benefit}>
        ✨ These constraints have been applied to your test scenarios to
        generate more realistic tests
      </div>
    </div>
  );
}
