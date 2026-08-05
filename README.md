# School Insights — Streamlit Prototype

Four role-based dashboards (School / Teacher / Student / Parent) built from
the same underlying student data, as a design step before migrating to
Frappe Insights.

## Run it

```bash
cd school_dashboard
python -m venv venv
venv\Scripts\Activate.ps1      # Windows PowerShell
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
streamlit run app.py
```

It'll open at `http://localhost:8501`. Use the sidebar to switch between
the four pages.

## Data sources (auto-detected in priority order)

Each time the app starts, it checks for data in this order:

### 1. Database (recommended for deployed apps)

If `.streamlit/secrets.toml` contains database credentials under `[db]`, the
app connects to MySQL/MariaDB and loads `student_master` and `subject_term`
tables directly.

**Local setup** (e.g., MariaDB Docker container):
1. Copy `.streamlit/secrets.toml.example` → `.streamlit/secrets.toml`
2. Fill in your local database credentials (usually `localhost` and `3306`)
3. Restart the app — it will connect and use your database automatically

**Streamlit Cloud deployment**:
1. Push your code to GitHub (`.streamlit/secrets.toml` is in `.gitignore`)
2. In Streamlit Cloud, go to your app's Settings → Secrets
3. Copy the contents of `.streamlit/secrets.toml.example`, update with your
   cloud-hosted database credentials, and paste into the Secrets manager
4. Redeploy — the app will use those credentials for all viewers

**Database schema**: The app expects two tables:
- `student_master`: columns matching the real-data loader output (UPN, yearGroup,
  regGroup, House, Sex, Attendance (%), Previous year attainment (%),
  current (%), predicted (%), teacherTarget (%), performance_band, at_risk)
- `subject_term`: one row per (student, subject, term) with columns UPN,
  subjectName, teacherName, term, sheetPercentage, predicted (%), teacherTarget (%)

### 2. CSV files (for one-time testing or offline use)

Drop `MSB_Private_School_2024-25_MASTER_ANON.csv` and
`ReportExplorer_MASTER_ANON.csv` into `data/`. The app detects them and uses
real data, no code changes needed.

The real-data loader in `utils/data_utils.py` (`_load_real_data()`) mirrors
notebook 3's cleaning and aggregation logic exactly:
- `current (%)`, `predicted (%)`, and `teacherTarget (%)` are constant per
  (student, subject) — not per-term — so they're averaged once per student
  for `student_master`
- The real per-term score is `sheetPercentage`, pulled from `sheetName` rows
  containing "Continuous Assessment", with term (T1/T2/T3) extracted via
  regex, for `subject_term`
- `Class Teacher Comments` and `Progress Test` rows are excluded (not
  percentage-graded subjects)
- Percent-string columns in the ReportExplorer file are converted to numeric
  the same way the EDA notebook does

### 3. Synthetic demo data (fallback)

If neither database nor CSV files are available, the app generates safe
synthetic data with the identical schema.

---

**Visibility note**: Database credentials and CSV data control *where the app
loads from*, not *who can see the app*. For Streamlit Cloud, you still need to
set the app to **Private** with a viewer allow-list in the sharing settings to
restrict who can access the dashboard itself.

## What's deliberately left out (by design, not oversight)

- **House** is not used as a comparison dimension anywhere — statistical
  testing found no real academic signal in it, so showing it would imply a
  pattern that isn't there.
- **Students never see each other's individual data.** Peer comparison is
  shown as a band (top/middle/bottom third), never a name or exact rank.
- **Teachers are never ranked by name against each other** — only an
  anonymized range, with "you" marked, to avoid the same demotivation risk
  ranking has for students.
- Wellbeing, staffing, admissions, finance, and facilities data aren't in
  this dataset at all — the School view has an expander that says so
  explicitly rather than pretending those questions are answered.

## Structure

```
app.py                  <- landing page / role picker
pages/
  1_School.py
  2_Teacher.py
  3_Student.py
  4_Parent.py
utils/
  data_utils.py          <- data loading, cleaning, demo generator
  metrics.py              <- shared calculations (calibration, growth, bands)
data/                    <- put real CSVs here when ready
```

## Next step: Frappe Insights

Once the layout/metrics are approved here, the plan is:
1. Containerize this app with Docker
2. Map each chart above to its Frappe Insights equivalent
3. Replace the sidebar role-selector with real role-based auth
