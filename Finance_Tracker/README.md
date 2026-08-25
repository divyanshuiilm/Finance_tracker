# Student Finance Manager 💰

A secure, full-featured personal finance tracker and planner tailored for college students in India.

---

## 🌟 Key Features

* **Real-time Dashboard & Safe-to-Spend**: Calculates available money, remaining monthly budget, daily safe-to-spend allowance, and emergency buffer protections.
* **Direct Dashboard Actions**: Edit or delete mistaken transactions directly from the Recent Transactions card on your homepage.
* **Phase 13 Multi-User Security & Isolation**: Individual user accounts with password hashing, per-user data isolation, CSRF protection, and IDOR prevention.
* **Phase 14 UPI Screenshot OCR Scanner**: Upload Google Pay, PhonePe, Paytm, or BHIM payment screenshots to automatically extract amount, merchant, date, and predict categories.
* **Phase 15 AI Financial Assistant**: Interactive chat widget on the dashboard for answering purchase questions (*"Can I afford ₹500 shoes?"*), explaining top expenses, and planning weekly allowances.
* **Budgets & Alerts**: Category and overall monthly budgets with 80% warning and 100% exceeded thresholds.
* **Savings Goals**: Goal deadlines, monthly required contributions, and progress tracking.
* **Recurring Commitments & Debts**: Track subscriptions, SIPs, recharges, and money lent or borrowed from friends.
* **Analytics & Smart Insights**: Category bar charts, monthly trends, and rule-based savings tips.
* **CSV Export**: 1-click backup of all personal transaction records.

---

## 💻 Local Development Setup

1. **Clone the repository** and open the project directory in terminal / PowerShell.
2. **Create & activate the virtual environment**:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install dependencies**:

   ```powershell
   pip install -r requirements.txt
   ```

4. **Start the application**:

   ```powershell
   python app.py
   ```

5. Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 🧪 Run Automated Tests

To execute the test suite (testing authentication, multi-user isolation, CRUD operations, OCR parsing, and the AI assistant):

```powershell
python -m unittest discover -s tests
```

---

## 🚀 Cloud Deployment Guide

### Option A: Deploy to Render.com (Recommended for SQLite persistence)

1. Push your code to GitHub.
2. Go to [Render.com](https://render.com) and click **New → Web Service**.
3. Connect your GitHub repository.
4. Render automatically detects [`render.yaml`](file:///c:/Users/hp/OneDrive/Documents/ChatGPT/Finance_Tracker/render.yaml) and [`Procfile`](file:///c:/Users/hp/OneDrive/Documents/ChatGPT/Finance_Tracker/Procfile).
5. Click **Create Web Service**. Your app will be live with full persistent storage!

### Option B: Deploy to Vercel

1. Push your code to GitHub.
2. Go to [Vercel.com](https://vercel.com) and import the repository.
3. Vercel automatically uses [`vercel.json`](file:///c:/Users/hp/OneDrive/Documents/ChatGPT/Finance_Tracker/vercel.json) and configures the Python serverless runtime.
4. Click **Deploy**.

---

## 🛡️ Security Note

* Never commit `.env` or production secrets to public repositories.
* Use `FLASK_SECRET_KEY` in environment variables when deploying online.
