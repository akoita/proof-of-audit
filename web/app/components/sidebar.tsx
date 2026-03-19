"use client";

type SidebarProps = {
  activeView: string;
  onViewChange: (view: string) => void;
  onNewClaim: () => void;
};

const NAV_ITEMS = [
  { id: "workbench",  label: "Workbench",  icon: "📝" },
  { id: "published",  label: "Published",  icon: "✓" },
  { id: "disputed",   label: "Disputed",   icon: "⚖" },
  { id: "reputation", label: "Reputation", icon: "🛡" },
  { id: "archive",    label: "Archive",    icon: "📦" },
] as const;

export function Sidebar({ activeView, onViewChange, onNewClaim }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">🔐</div>
          <div className="sidebar-logo-text">
            <h3>Audit Lifecycle</h3>
            <p>Precision Forensics</p>
          </div>
        </div>
        <button className="sidebar-new-btn" type="button" onClick={onNewClaim}>
          <span>+</span> New Audit Claim
        </button>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className="sidebar-nav-item"
            data-active={activeView === item.id}
            onClick={() => onViewChange(item.id)}
          >
            <span className="icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <button
          className="sidebar-nav-item"
          data-active={activeView === "docs"}
          type="button"
          onClick={() => onViewChange("docs")}
        >
          <span className="icon">📖</span>
          <span>Technical Docs</span>
        </button>
        <a
          className="sidebar-nav-item"
          href="https://github.com/akoita/proof-of-audit/issues"
          target="_blank"
          rel="noopener noreferrer"
        >
          <span className="icon">💬</span>
          <span>Support</span>
        </a>
      </div>
    </aside>
  );
}
