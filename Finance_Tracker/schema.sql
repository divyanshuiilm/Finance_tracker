-- Users table for multi-user authentication.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Each row represents one income or expense record belonging to a specific user.
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount REAL NOT NULL CHECK (amount > 0),
    transaction_date TEXT NOT NULL,
    category TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    merchant TEXT,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A budget may apply to the full month or one category within that month for a user.
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    budget_month TEXT NOT NULL,
    category TEXT,
    amount REAL NOT NULL CHECK (amount >= 0)
);

-- Only one overall budget or category budget may exist for each month per user.
CREATE UNIQUE INDEX IF NOT EXISTS idx_budgets_user_month_category
ON budgets (user_id, budget_month, IFNULL(category, ''));

-- A savings goal, such as a laptop or emergency fund for a user.
CREATE TABLE IF NOT EXISTS savings_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    target_amount REAL NOT NULL CHECK (target_amount > 0),
    saved_amount REAL NOT NULL DEFAULT 0 CHECK (saved_amount >= 0),
    deadline TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Expected income or expenses that repeat over time for a user.
CREATE TABLE IF NOT EXISTS recurring_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('income', 'expense')),
    amount REAL NOT NULL CHECK (amount > 0),
    category TEXT NOT NULL,
    payment_method TEXT NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'monthly',
    next_due_date TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- Money owed by the student or owed to the student for a user.
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    debt_type TEXT NOT NULL CHECK (debt_type IN ('lent', 'borrowed')),
    person TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK (status IN ('unpaid', 'partially_paid', 'paid')),
    note TEXT
);

-- Per-user planning settings for values such as the emergency buffer.
CREATE TABLE IF NOT EXISTS settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    emergency_buffer REAL NOT NULL DEFAULT 0 CHECK (emergency_buffer >= 0),
    monthly_savings_target REAL NOT NULL DEFAULT 0 CHECK (monthly_savings_target >= 0)
);
