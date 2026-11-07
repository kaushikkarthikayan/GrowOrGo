"""Skills taxonomy: one canonical name per skill, with the other ways people write it.
Used to (1) find skills in text without AI and (2) clean up skill names the AI returns,
so "JS", "Javascript" and "ECMAScript" all count as the same skill when matching jobs.
Add more skills here any time - the format is  "Canonical Name": [aliases...]."""
import re

from rapidfuzz import fuzz, process

TAXONOMY: dict[str, list[str]] = {
    # Programming
    "Python": ["python3", "py"],
    "R": ["r programming", "rstudio"],
    "SQL": ["structured query language", "t-sql", "tsql", "pl/sql", "plsql"],
    "Java": ["core java", "j2ee"],
    "JavaScript": ["js", "javascript", "ecmascript", "es6"],
    "TypeScript": ["ts"],
    "C": ["c language"],
    "C++": ["cpp", "c plus plus"],
    "C#": ["c sharp", "csharp", ".net c#"],
    "Go": ["golang"],
    "Scala": [],
    "Bash": ["shell scripting", "shell", "bash scripting"],
    "VBA": ["excel vba", "macros"],
    # Data & analytics
    "Excel": ["ms excel", "microsoft excel", "advanced excel", "spreadsheets"],
    "Power BI": ["powerbi", "power-bi", "microsoft power bi"],
    "Tableau": [],
    "Looker": ["looker studio", "google data studio"],
    "DAX": [],
    "Pandas": [],
    "NumPy": ["numpy"],
    "Data Visualization": ["data visualisation", "dashboards", "dashboarding", "data viz"],
    "Data Analysis": ["data analytics", "analytics", "exploratory data analysis", "eda"],
    "Data Cleaning": ["data wrangling", "data preprocessing", "data cleansing", "cleaned data", "cleaning data", "clean data",
                      "cleaned customer data", "cleaned the data", "data quality"],
    "Statistics": ["statistical analysis", "hypothesis testing", "a/b testing", "ab testing"],
    "ETL": ["extract transform load", "data pipelines", "elt"],
    "Data Warehousing": ["data warehouse", "dimensional modelling", "dimensional modeling"],
    "Snowflake": [],
    "BigQuery": ["google bigquery"],
    "Apache Spark": ["spark", "pyspark"],
    "Hadoop": [],
    "Airflow": ["apache airflow"],
    "dbt": ["data build tool"],
    # Databases
    "PostgreSQL": ["postgres", "psql"],
    "MySQL": [],
    "MongoDB": ["mongo"],
    "SQL Server": ["mssql", "microsoft sql server"],
    "Oracle Database": ["oracle db", "oracle sql"],
    "Redis": [],
    # ML / AI
    "Machine Learning": ["ml"],
    "Deep Learning": ["dl", "neural networks"],
    "Scikit-learn": ["sklearn", "scikit learn"],
    "TensorFlow": ["tf", "keras"],
    "PyTorch": ["torch"],
    "NLP": ["natural language processing", "text mining"],
    "Computer Vision": ["opencv", "image processing"],
    "LLMs": ["large language models", "generative ai", "genai", "gpt", "prompt engineering"],
    "MLOps": ["model deployment", "mlflow"],
    "Time Series": ["forecasting", "time series analysis"],
    # Web & software
    "HTML": ["html5"],
    "CSS": ["css3", "tailwind", "tailwind css", "bootstrap"],
    "React": ["react.js", "reactjs"],
    "Next.js": ["nextjs"],
    "Node.js": ["nodejs", "node", "express", "express.js"],
    "Django": [],
    "Flask": [],
    "FastAPI": [],
    "REST APIs": ["rest", "restful", "rest api", "api development"],
    "Git": ["github", "gitlab", "version control"],
    "Docker": ["containers", "containerization"],
    "Kubernetes": ["k8s"],
    "CI/CD": ["jenkins", "github actions", "continuous integration"],
    "Linux": ["unix", "ubuntu"],
    "Testing": ["software testing", "qa", "quality assurance", "manual testing"],
    "Test Automation": ["selenium", "automation testing", "pytest", "cypress", "playwright"],
    # Cloud
    "AWS": ["amazon web services", "ec2", "s3", "lambda"],
    "Azure": ["microsoft azure"],
    "Google Cloud": ["gcp", "google cloud platform"],
    # Business / CRM / PM
    "CRM": ["customer relationship management"],
    "Salesforce": [],
    "HubSpot": [],
    "Agile": ["scrum", "kanban", "sprint planning"],
    "Jira": [],
    "Project Management": ["pmp", "prince2"],
    "Stakeholder Management": ["stakeholder communication", "client management"],
    "Business Analysis": ["requirements gathering", "business analyst"],
    "Communication": ["presentation skills", "public speaking", "written communication"],
    "Teamwork": ["collaboration", "team player"],
    "Leadership": ["team leadership", "people management", "team management"],
    "Problem Solving": ["critical thinking", "analytical thinking"],
    "Customer Service": ["customer support", "client service"],
    # Design
    "Figma": [],
    "UI/UX Design": ["ui design", "ux design", "user experience", "user interface design", "wireframing"],
}

# Build lookup: lowercase alias -> canonical
_ALIAS: dict[str, str] = {}
for canon, aliases in TAXONOMY.items():
    _ALIAS[canon.lower()] = canon
    for a in aliases:
        _ALIAS[a.lower()] = canon

# Very short / ambiguous aliases only match in a "Skills" style line, not anywhere.
_AMBIGUOUS = {"r", "c", "go", "py", "ts", "tf", "ml", "dl", "js", "node", "shell", "rest",
              "qa", "spark", "torch", "s3", "lambda", "ec2", "gpt", "macros", "unix", "eda"}


def _pattern(alias: str) -> re.Pattern:
    # Word boundaries that also work for names like "C++", "C#", ".NET", "Next.js"
    return re.compile(r"(?<![\w+#.])" + re.escape(alias) + r"(?![\w+#])", re.IGNORECASE)


_PATTERNS = [(alias, canon, _pattern(alias)) for alias, canon in _ALIAS.items()]


def normalize_skill(name: str) -> str:
    """Map any spelling to the canonical skill name. Unknown skills are returned title-cased."""
    if not name:
        return name
    key = name.strip().lower()
    if key in _ALIAS:
        return _ALIAS[key]
    match = process.extractOne(key, _ALIAS.keys(), scorer=fuzz.ratio, score_cutoff=90)
    if match:
        return _ALIAS[match[0]]
    return name.strip()


def skills_in_line(line: str, in_skills_section: bool = False) -> set[str]:
    """Canonical skills mentioned in one line of text."""
    clean = line.strip()
    if not clean:
        return set()
    is_skill_line = in_skills_section or bool(
        re.match(r"^\s*(technical\s+)?(skills?|tools|technologies|tech stack)\b", clean, re.I)
    )
    found = set()
    for alias, canon, pat in _PATTERNS:
        if canon in found:
            continue
        if alias in _AMBIGUOUS and not is_skill_line:
            continue
        if pat.search(clean):
            found.add(canon)
    return found


def find_skills(text: str) -> dict[str, str]:
    """Rule-based skill finder. Returns {canonical_skill: first evidence line}."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        for s in skills_in_line(line):
            found.setdefault(s, line.strip()[:300])
    return found
