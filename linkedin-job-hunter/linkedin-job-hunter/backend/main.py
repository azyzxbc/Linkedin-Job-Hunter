from fastapi import FastAPI, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
from bs4 import BeautifulSoup
import asyncio
import re
from datetime import datetime
import urllib.parse

app = FastAPI(title="LinkedIn Job Hunter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─── CV keyword extraction ────────────────────────────────────────────────────

TECH_SKILLS = [
    # Languages
    "Python","JavaScript","TypeScript","Java","Go","Golang","Rust","C++","C#","Ruby","PHP","Swift","Kotlin","Scala","R","MATLAB","Bash","Shell","PowerShell",
    # Web
    "React","Vue","Angular","Next.js","Nuxt","Svelte","Node.js","Express","FastAPI","Django","Flask","Laravel","Spring","ASP.NET","GraphQL","REST","gRPC",
    # Cloud & DevOps
    "AWS","Azure","GCP","Google Cloud","Kubernetes","K8s","Docker","Terraform","Ansible","Puppet","Chef","Helm","ArgoCD","Flux","Pulumi",
    "CI/CD","Jenkins","GitHub Actions","GitLab CI","CircleCI","Travis CI","Bitbucket","Tekton",
    "DevOps","SRE","Platform Engineer","Cloud Engineer","MLOps","DataOps","FinOps","GitOps",
    # Observability
    "Prometheus","Grafana","Datadog","New Relic","Dynatrace","Splunk","ELK","Elasticsearch","Kibana","Logstash","Jaeger","OpenTelemetry",
    # Databases
    "PostgreSQL","MySQL","MariaDB","MongoDB","Redis","Cassandra","DynamoDB","BigQuery","Snowflake","Oracle","SQL Server","SQLite","InfluxDB","TimescaleDB",
    # Data
    "Apache Spark","Kafka","Airflow","dbt","Hadoop","Flink","Databricks","Pandas","NumPy","Data Engineering","Data Science","ETL","ELT",
    # ML/AI
    "Machine Learning","Deep Learning","TensorFlow","PyTorch","scikit-learn","Keras","NLP","LLM","OpenAI","Hugging Face","Computer Vision","RAG",
    # Security
    "DevSecOps","Security","Cybersecurity","SIEM","SOC","Penetration Testing","IAM","Zero Trust","Vault",
    # Networking & Infra
    "Linux","Nginx","HAProxy","Istio","Envoy","Service Mesh","VPN","BGP","DNS","TCP/IP",
    # Methodologies
    "Agile","Scrum","Kanban","SAFe","ITIL","SLA","SLO","SLI",
    # Job titles (to detect seniority / domain)
    "DevOps Engineer","Cloud Architect","Solutions Architect","Data Engineer","Data Scientist",
    "Backend Developer","Frontend Developer","Full Stack","Software Engineer","Platform Engineer",
    "Site Reliability","Security Engineer","Network Engineer","System Administrator",
]

def extract_cv_keywords(cv_text: str) -> list[str]:
    """Extract recognisable tech skills from raw CV text using word-boundary matching."""
    found = []
    seen_lower = set()
    for skill in TECH_SKILLS:
        pattern = r'(?i)\b' + re.escape(skill) + r'\b'
        if re.search(pattern, cv_text):
            key = skill.lower()
            if key not in seen_lower:
                seen_lower.add(key)
                found.append(skill)
    return found


# ─── Google search (site:linkedin.com/jobs) ───────────────────────────────────

async def search_google(keywords: list[str], location: str) -> list[dict]:
    query_parts = keywords + ([location] if location else [])
    query = " ".join(query_parts)
    search_query = f'site:linkedin.com/jobs/view {query}'
    url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}&num=30&hl=en"

    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            for g in soup.select("div.g"):
                title_el = g.select_one("h3")
                link_el = g.select_one("a")
                snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")

                if not title_el or not link_el:
                    continue

                href = link_el.get("href", "")
                if "linkedin.com/jobs" not in href:
                    continue

                title = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # Clean title: remove " | LinkedIn" suffix
                title = re.sub(r"\s*[|\-]\s*LinkedIn.*$", "", title).strip()

                results.append({
                    "source": "google",
                    "title": title,
                    "company": extract_company_from_snippet(snippet),
                    "location": extract_location_from_snippet(snippet, location),
                    "snippet": snippet,
                    "url": href,
                    "posted": extract_date_from_snippet(snippet),
                })
    except Exception as e:
        print(f"Google search error: {e}")

    return results


# ─── LinkedIn public jobs search ─────────────────────────────────────────────

async def search_linkedin(keywords: list[str], location: str, experience: str) -> list[dict]:
    keyword_str = urllib.parse.quote(" ".join(keywords))
    location_str = urllib.parse.quote(location or "Tunisia")

    exp_map = {
        "internship": "1",
        "junior": "2",
        "mid": "3",
        "senior": "4",
        "lead": "5",
    }
    exp_code = exp_map.get(experience.lower(), "") if experience else ""
    exp_param = f"&f_E={exp_code}" if exp_code else ""

    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword_str}&location={location_str}{exp_param}&start=0"

    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            for card in soup.select("li"):
                title_el = card.select_one("h3.base-search-card__title, h3")
                company_el = card.select_one("h4.base-search-card__subtitle, h4")
                location_el = card.select_one("span.job-search-card__location, span.job-result-card__location")
                date_el = card.select_one("time")
                link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")

                if not title_el:
                    continue

                href = link_el.get("href", "") if link_el else ""
                # Clean tracking params
                href = href.split("?")[0] if href else ""

                results.append({
                    "source": "linkedin",
                    "title": title_el.get_text(strip=True),
                    "company": company_el.get_text(strip=True) if company_el else "",
                    "location": location_el.get_text(strip=True) if location_el else location,
                    "snippet": "",
                    "url": href or f"https://www.linkedin.com/jobs/search/?keywords={keyword_str}&location={location_str}",
                    "posted": date_el.get("datetime", "") if date_el else "",
                })
    except Exception as e:
        print(f"LinkedIn scrape error: {e}")

    return results


# ─── LinkedIn hiring posts (recruiter/people posts) ──────────────────────────

async def _google_hiring_query(search_query: str) -> list[dict]:
    """Run a single Google search and return parsed hiring post results."""
    url = f"https://www.google.com/search?q={urllib.parse.quote(search_query)}&num=20&hl=en"
    results = []
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")

            for g in soup.select("div.g"):
                title_el   = g.select_one("h3")
                link_el    = g.select_one("a")
                snippet_el = g.select_one("div.VwiC3b, span.aCOpRe, div[data-sncf]")

                if not title_el or not link_el:
                    continue

                href = link_el.get("href", "")
                if "linkedin.com" not in href:
                    continue

                title   = title_el.get_text(strip=True)
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                # Extract person name from title e.g. "John Doe on LinkedIn: We are hiring..."
                m = re.match(r"^(.+?)\s+(on LinkedIn|posted|shared)", title, re.IGNORECASE)
                person = m.group(1).strip() if m else re.sub(r"\s*[|\-]\s*LinkedIn.*$", "", title).strip()

                results.append({
                    "person":  person,
                    "title":   title,
                    "snippet": snippet,
                    "url":     href,
                    "posted":  extract_date_from_snippet(snippet),
                })
    except Exception as e:
        print(f"Hiring search error ({search_query[:40]}): {e}")
    return results


async def search_hiring_posts(keywords: list[str], location: str) -> list[dict]:
    query = " ".join(keywords + ([location] if location else []))

    # Two separate clean queries — Google handles these much better than OR site:
    q1 = f'site:linkedin.com/posts hiring {query}'
    q2 = f'site:linkedin.com/in hiring {query}'

    r1, r2 = await asyncio.gather(_google_hiring_query(q1), _google_hiring_query(q2))

    combined = r1 + r2
    # Deduplicate by URL
    seen, out = set(), []
    for r in combined:
        key = r["url"].split("?")[0]
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_company_from_snippet(snippet: str) -> str:
    patterns = [r"^([^·\-\n]+?)\s*[·\-]", r"at\s+([A-Z][^\s,]+(?:\s+[A-Z][^\s,]+)*)"]
    for p in patterns:
        m = re.search(p, snippet)
        if m:
            return m.group(1).strip()
    return ""

def extract_location_from_snippet(snippet: str, fallback: str) -> str:
    m = re.search(r"(Tunis(?:ia)?|Sfax|Sousse|Nabeul|Bizerte|Remote)", snippet, re.IGNORECASE)
    return m.group(0) if m else fallback

def extract_date_from_snippet(snippet: str) -> str:
    m = re.search(r"(\d+\s+(?:hour|day|week|month)s?\s+ago)", snippet, re.IGNORECASE)
    return m.group(0) if m else ""

def deduplicate(results: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in results:
        key = re.sub(r"[^a-z0-9]", "", r["title"].lower()[:40])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ─── API routes ───────────────────────────────────────────────────────────────

@app.get("/api/search")
async def search(
    keywords: str = Query(..., description="Comma-separated keywords"),
    location: str = Query("Tunisia", description="Location"),
    experience: str = Query("", description="junior | mid | senior | lead"),
):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return {"results": [], "total": 0, "error": "No keywords provided"}

    google_task = search_google(kw_list, location)
    linkedin_task = search_linkedin(kw_list, location, experience)

    google_results, linkedin_results = await asyncio.gather(google_task, linkedin_task)

    combined = linkedin_results + google_results
    combined = deduplicate(combined)

    return {
        "results": combined,
        "total": len(combined),
        "linkedin_count": len(linkedin_results),
        "google_count": len(google_results),
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/hiring-posts")
async def hiring_posts(
    keywords: str = Query(..., description="Comma-separated keywords"),
    location: str = Query("Tunisia", description="Location"),
):
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kw_list:
        return {"results": [], "total": 0, "error": "No keywords provided"}

    results = await search_hiring_posts(kw_list, location)

    return {
        "results": results,
        "total": len(results),
    }



@app.post("/api/cv-search")
async def cv_search(payload: dict = Body(...)):
    cv_text   = payload.get("cv_text", "").strip()
    location   = payload.get("location", "Tunisia")
    experience = payload.get("experience", "")

    if not cv_text:
        return {"error": "CV text is empty", "keywords": [], "results": [], "total": 0}

    keywords = extract_cv_keywords(cv_text)
    if not keywords:
        return {
            "error": "No recognisable tech skills found. Try pasting more of your CV.",
            "keywords": [],
            "results": [],
            "total": 0,
        }

    # Use top 6 most specific keywords for search
    search_kw = keywords[:6]

    google_task   = search_google(search_kw, location)
    linkedin_task = search_linkedin(search_kw, location, experience)
    google_results, linkedin_results = await asyncio.gather(google_task, linkedin_task)

    combined = linkedin_results + google_results
    combined = deduplicate(combined)

    return {
        "keywords":       keywords,          # all extracted skills
        "results":        combined,
        "total":          len(combined),
        "linkedin_count": len(linkedin_results),
        "google_count":   len(google_results),
    }


# ─── Serve frontend ───────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="/app/frontend"), name="static")

@app.get("/")
async def root():
    return FileResponse("/app/frontend/index.html")
