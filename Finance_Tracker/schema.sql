-- A local account protects the single-user version of this application.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Each row represents one income or expense record.
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount REAL NOT NULL CHECK (amount > 0),
    transaction_date TEXT NOT NULL,
    category TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    merchant TEXT,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A budget may apply to the full month or one category within that month.
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_month TEXT NOT NULL,
    category TEXT,
    amount REAL NOT NULL CHECK (amount >= 0)
);

-- Only one overall budget or category budget may exist for each month.
CREATE UNIQUE INDEX IF NOT EXISTS idx_budgets_month_category
ON budgets (budget_month, IFNULL(category, ''));

-- A savings goal, such as a laptop or emergency fund.
CREATE TABLE IF NOT EXISTS savings_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL CHECK (target_amount > 0),
    saved_amount REAL NOT NULL DEFAULT 0 CHECK (saved_amount >= 0),
    deadline TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Expected income or expenses that repeat over time.
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount REAL NOT NULL CHECK (amount > 0),
    category TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'monthly',
    next_due_date TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- Money owed by the student or owed to the student.
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    debt_type TEXT NOT NULL CHECK (debt_type IN ('lent', 'borrowed')),
    person TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'partially_paid', 'paid')),
    note TEXT
);

-- One-row settings table for values such as the emergency buffer.
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    emergency_buffer REAL NOT NULL DEFAULT 0 CHECK (emergency_buffer >= 0),
    monthly_savings_target REAL NOT NULL DEFAULT 0 CHECK (monthly_savings_target >= 0)
);
