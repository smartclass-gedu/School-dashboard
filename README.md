# School Insights — Streamlit Prototype

Five role-based dashboards (School / Teacher / Student / Parent / Benchmark)
built from the same underlying student data, as a design step before
migrating to Frappe Insights.

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

## Demo data vs. real data

To use real data:
1. Drop `MSB_Private_School_2024-25_MASTER_ANON.csv` and
   `ReportExplorer_MASTER_ANON.csv` into `data/`
2. Restart the app — it detects the files automatically and switches from
   synthetic demo data to real data, no code changes needed. Each page's
   subtitle shows "· demo data" or "· live data" so it's always clear which
   one you're looking at.

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

If your data columns differ from this (e.g. the Grade 1–7 primary export
uses a different schema than the Grade 7–11 file), that's the function to
extend — it currently assumes both files share the schema documented in the
EDA notebooks.

## Live database (optional, for deployment)

To load data from a hosted MySQL/MariaDB database instead of (or in addition
to) local CSVs, the app checks for a `[db]` section in Streamlit's secrets
file.

**Local testing with a database:**
1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
2. Fill in the `[db]` section with your local MariaDB Docker container's
   connection details (e.g. `host = "localhost"`, the mapped port, etc.)
3. On the next app run, it will connect to your database automatically.
   No code changes or restart-order dependencies needed.

**Deploying to Streamlit Community Cloud:**
1. In your deployed app's **Settings → Secrets**, paste the same `[db]` TOML
   block, but with `host`/credentials pointed at your cloud-hosted database
   instead of `localhost`.
2. The app will pick up those secrets on the next reload or redeploy.

**Data source priority order:**
The app checks for data in this order: (1) MySQL/MariaDB via `st.secrets["db"]`
if configured, (2) local CSV files in `data/`, (3) synthetic demo data. If
more than one source is present, the earlier one wins.

**Important:** Secrets control *where data loads from*, not *who can see the
app*. If the data shouldn't be publicly visible, separately set the app to
**Private** with a viewer allow-list in Streamlit Cloud's sharing settings.

## External Benchmark Alignment (CAT4) — KHDA grade-inflation check

The **📐 Benchmark** page compares internal grades against CAT4, an
externally-standardized, content-free cognitive-ability battery — the kind
of external reference point KHDA inspectors check internal marking against
to detect grade inflation.

- Source data: the real `CAT4` (letter grade) and `externalTarget (%)`
  columns already present in `MSB_Private_School_2024-25_MASTER_ANON.csv`,
  constant per (student, subject) the same way `current (%)` is. **Note:**
  the source data has one CAT4-derived expected grade per subject, not the
  four separate Verbal/Quantitative/Non-Verbal/Spatial battery subscores —
  the page compares internal-vs-external at the subject level, not the raw
  cognitive-domain level.
- Coverage: Years 7–10 only, ~310 of 1072 students, 25 subjects — CAT4
  isn't administered school-wide, so this page is never a whole-school
  comparison the way the School page's other charts are.
- `gap (pp) = internal (%) − external (CAT4-predicted) (%)`. A configurable
  threshold (default 10pp) flags student-subject pairs where the internal
  grade runs well ahead of the external benchmark. The ranked table groups
  by subject + teacher, since that's the grain a marking-consistency review
  actually operates at.
- Demo mode synthesizes a comparable dataset (same coverage shape, with a
  deliberate bias baked into a subset of teachers) so the page has
  something to review before real data is wired in.
- `utils/data_utils.py`'s `load_benchmark_data()` follows the same
  DB > CSV > demo priority as `load_data()`, and `etl_to_mariadb.py` writes
  the same table (`external_benchmark`) to MariaDB so Frappe Insights can
  read it too.

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
  5_Benchmark.py          <- CAT4 external benchmark vs. internal grades (KHDA)
utils/
  data_utils.py          <- data loading, cleaning, demo generator
  metrics.py              <- shared calculations (calibration, growth, bands)
data/                    <- put real CSVs here when ready
etl_to_mariadb.py         <- also writes the external_benchmark table
```

## Next step: Frappe Insights

Once the layout/metrics are approved here, the plan is:
1. Containerize this app with Docker
2. Map each chart above to its Frappe Insights equivalent
3. Replace the sidebar role-selector with real role-based auth
