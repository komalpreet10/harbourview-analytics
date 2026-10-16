# Harbourview Analytics

Analytics for Harbourview House using synthetic resident data.

- **Task A:** `harbourview_analysis.ipynb` — descriptive analysis for 2025.
- **Task B:** `app.py` — Streamlit assistant: question → validated JSON → read-only MongoDB aggregation → chart.
- **Design:** `design.md`.
- **Write-up and Task C:** `writeup.md`.

## Project structure

```text
Axon/
├── app.py
├── harbourview_analysis.ipynb
├── data/harbourview_residents.csv
├── src/
│   ├── agent.py
│   ├── schemas.py
│   ├── validator.py
│   ├── database.py
│   ├── charts.py
│   └── privacy.py
├── scripts/
│   ├── setup_mongodb.py
│   ├── generate_data.py
│   └── check_setup.py
├── tests/
├── design.md
├── writeup.md
├── requirements.txt
├── requirements-notebook.txt
├── .env.example
└── .gitignore
```

## Setup

Use Python 3.11. Run commands from the project root.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Place the supplied CSV at `data/harbourview_residents.csv`. It is excluded from Git.

## MongoDB

Start Docker Desktop. Choose an admin password:

```bash
printf "MongoDB admin password: "
read -s MONGO_SETUP_PASSWORD
export MONGO_SETUP_PASSWORD
```

```bash
docker run -d --name axon-mongodb \
  -p 127.0.0.1:27017:27017 \
  -v axon-mongodb-data:/data/db \
  -e MONGO_INITDB_ROOT_USERNAME=setup_admin \
  -e MONGO_INITDB_ROOT_PASSWORD="$MONGO_SETUP_PASSWORD" \
  mongo:8.0
```

For an existing container, run `docker start axon-mongodb` instead.

Create a local `.env` with:

```dotenv
OPENAI_API_KEY=your-api-key
MONGODB_SETUP_URI=mongodb://setup_admin:ADMIN_PASSWORD@localhost:27017/?authSource=admin
MONGODB_READER_PASSWORD=READER_PASSWORD
MONGODB_READ_URI=mongodb://analytics_app:READER_PASSWORD@localhost:27017/?authSource=harbourview
```

Replace placeholders with your credentials. Use the same reader password in both settings and URL-encode passwords in connection URIs. Never commit `.env`.

Import the CSV and create the read-only account:

```bash
python scripts/setup_mongodb.py
```

## Run the app

```bash
python -m streamlit run app.py
```

Example questions:
- How many residents were admitted in 2025?
- Show monthly admissions in 2025 as a line chart.
- What percentage of residents referred in 2025 were admitted by December 31, 2025?
- Show monthly occupancy in 2025.
- What was the median completed stay for residents discharged in 2025?
- How many residents admitted in 2025 had their entrance fee waived?
- How many residents admitted in 2025 have a recorded six-month outcome of lost to follow-up?
- How many residents were successful in 2025? (asks for clarification)

Use synthetic questions only. Local privacy screening is implemented, but it may miss some personal or health information.

## Checks

```bash
python scripts/check_setup.py --database
python -m pytest -q
```
