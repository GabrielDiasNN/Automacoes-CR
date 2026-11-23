import { type ReactNode } from "react";
import styles from "./Tabs.module.css";

export interface TabItem<T extends string = string> {
  id: T;
  label: string;
  icon?: ReactNode;
  badge?: string | number | undefined;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  activeId: T;
  onChange: (id: T) => void;
  ariaLabel?: string;
}

export function Tabs<T extends string>({
  items,
  activeId,
  onChange,
  ariaLabel = "Seções da tela",
}: TabsProps<T>) {
  return (
    <div className={styles.tablist} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const selected = item.id === activeId;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected}
            className={`${styles.tab} ${selected ? styles.tabActive : ""}`}
            onClick={() => onChange(item.id)}
          >
            {item.icon && (
              <span className={styles.icon} aria-hidden="true">
                {item.icon}
              </span>
            )}
            <span>{item.label}</span>
            {item.badge !== undefined && item.badge !== "" && (
              <span className={styles.badge}>{item.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
