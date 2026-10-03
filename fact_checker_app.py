"""
TruthCheck AI v2

Install:  pip install streamlit groq requests ddgs
Keys:     put them in .streamlit/secrets.toml (never in the code):
              GROQ_API_KEY = "..."
              GOOGLE_FACT_CHECK_API_KEY = "..."
Run:      streamlit run fact_checker_app_fixed.py
"""
import base64
import html
import json
import os
import re
from datetime import date
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
import streamlit as st
from groq import Groq

try:
    from ddgs import DDGS  # new package name
except ImportError:
    from duckduckgo_search import DDGS  # older name

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="TruthCheck", page_icon="🌸", layout="centered",
                   initial_sidebar_state="collapsed")


def get_secret(name: str) -> str:
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, "")


GROQ_API_KEY = "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"
FACT_CHECK_KEY = "AIzaSyClVZXSyi1PfgwIVTAmJsY4u8N_5Cf92BQ"

TEXT_MODEL = "llama-3.3-70b-versatile"
# Per Groq's vision docs, this is the current image-capable model. The Llama 4
# IDs stay as fallbacks; analyze_screenshot also skips any ID your account lacks.
VISION_MODELS = [
    "qwen/qwen3.8-27b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
]

# Domains treated as credible when they appear in search results.
CREDIBLE_DOMAINS = (
    "rappler.com", "inquirer.net", "philstar.com", "gmanetwork.com", "abs-cbn.com",
    "pna.gov.ph", "mb.com.ph", "manilatimes.net", "pep.ph", "cnnphilippines.com",
    "bsp.gov.ph", "deped.gov.ph", "doh.gov.ph", "pagasa.dost.gov.ph", "phivolcs.dost.gov.ph",
    "gov.ph", "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "aljazeera.com", "who.int", "cdc.gov", "nasa.gov", "snopes.com", "factcheck.org",
    "politifact.com", "vera-files.org", "verafiles.org", "tsek.ph", "afp.com",
    "tribune.net.ph", "abante.com.ph", "dzrh.com.ph", "bworldonline.com", "sunstar.com.ph",
    "newswatchplus.ph", "thediplomat.com", "straitstimes.com",
)
OUTLETS = {
    "inquirer": "inquirer.net", "rappler": "rappler.com", "philstar": "philstar.com",
    "gma news": "gmanetwork.com", "abs-cbn": "abs-cbn.com", "philippine news agency": "pna.gov.ph",
    "manila bulletin": "mb.com.ph", "manila times": "manilatimes.net",
    "cnn philippines": "cnnphilippines.com", "reuters": "reuters.com",
    "associated press": "apnews.com", "bbc": "bbc.com", "tribune": "tribune.net.ph",
    "abante": "abante.com.ph", "sunstar": "sunstar.com.ph",
}
DEBUNK_WORDS = ("fake news", "hoax", "false claim", "fact check", "fact-check", "debunk",
                "misleading", "scam", "fabricated", "satire")
NEGATIVE_RATINGS = ("false", "fake", "hoax", "scam", "pants on fire", "fabricated",
                    "misleading", "satire", "no evidence", "incorrect", "unproven")
POSITIVE_RATINGS = ("true", "correct", "accurate", "legit", "real")

THEME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
:root{--bg:#FFF8FB;--card:#FFFFFF;--ink:#3A2A33;--muted:#8F7A86;--line:#F4DCE7;--pink:#E85D93;--pink-dark:#D1447D;--pink-soft:#FDEAF2;}
html,body,[class*="css"],.stApp{font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif;color:var(--ink);}
.stApp{background:var(--bg);}
#MainMenu,footer,[data-testid="stToolbar"],[data-testid="stDecoration"]{display:none;}
header[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:720px;padding-top:2.2rem;padding-bottom:4rem;}
[data-testid="stSidebar"]{background:#fff;border-right:1px solid var(--line);}
.tc-hero{text-align:center;margin:0 0 1.8rem;}
.tc-badge{display:inline-block;padding:.25rem .85rem;border-radius:999px;background:var(--pink-soft);color:var(--pink-dark);font-size:.72rem;font-weight:700;letter-spacing:.1em;}
.tc-hero h1{font-size:2.5rem;font-weight:700;margin:.7rem 0 .35rem;letter-spacing:-.03em;color:var(--ink);padding:0;}
.tc-hero p{color:var(--muted);font-size:.98rem;margin:0 auto;max-width:460px;line-height:1.55;}
.stTabs [data-baseweb="tab-list"]{gap:.3rem;border-bottom:1px solid var(--line);}
.stTabs [data-baseweb="tab"]{height:2.6rem;padding:0 1rem;background:transparent;color:var(--muted);font-weight:500;}
.stTabs [aria-selected="true"]{color:var(--pink-dark) !important;}
.stTabs [data-baseweb="tab-highlight"]{background-color:var(--pink) !important;}
.stTabs [data-baseweb="tab-border"]{display:none;}
div[data-baseweb="textarea"]{background:#fff;border:1px solid var(--line);border-radius:16px;}
div[data-baseweb="textarea"]:focus-within{border-color:var(--pink);box-shadow:0 0 0 3px rgba(232,93,147,.14);}
.stTextArea textarea{background:transparent;color:var(--ink);font-size:.96rem;padding:1rem;line-height:1.6;}
[data-testid="stFileUploaderDropzone"]{background:#fff;border:1.5px dashed #F2B8D0;border-radius:16px;padding:1.6rem;}
[data-testid="stFileUploaderDropzone"] button{border-radius:999px;border:1px solid var(--line);color:var(--pink-dark);background:#fff;}
[data-testid="stFileUploaderDropzone"] button:hover{border-color:var(--pink);color:var(--pink-dark);}
.stButton>button{background:var(--pink);color:#fff;border:none;border-radius:999px;padding:.72rem 1.4rem;font-weight:600;font-size:1rem;box-shadow:0 8px 20px rgba(232,93,147,.28);transition:all .15s ease;}
.stButton>button p{color:#fff;}
.stButton>button:hover{background:var(--pink-dark);color:#fff;transform:translateY(-1px);}
.stButton>button:focus:not(:active){color:#fff;border:none;box-shadow:0 8px 20px rgba(232,93,147,.28);}
.stButton>button:active{background:var(--pink-dark);color:#fff;transform:translateY(0);}
[data-testid="stExpander"]{border:1px solid var(--line);border-radius:14px;background:#fff;}
[data-testid="stExpander"] summary{color:var(--muted);font-size:.9rem;}
[data-testid="stAlert"]{border-radius:14px;}
[data-testid="stImage"] img{border-radius:14px;border:1px solid var(--line);}
.tc-card{background:var(--card);border:1px solid var(--line);border-radius:20px;padding:1.4rem 1.5rem;margin:1.2rem 0;box-shadow:0 10px 32px rgba(232,93,147,.07);}
.tc-verdict{display:flex;align-items:center;gap:.65rem;margin-bottom:.9rem;}
.tc-dot{width:12px;height:12px;border-radius:50%;flex:none;}
.tc-label{font-size:1.4rem;font-weight:700;letter-spacing:-.015em;}
.tc-conf{margin-left:auto;font-size:.82rem;color:var(--muted);font-weight:500;}
.tc-bar{height:6px;background:#F7E8EF;border-radius:999px;overflow:hidden;margin-bottom:1.1rem;}
.tc-bar>div{height:100%;border-radius:999px;}
.tc-text{font-size:.97rem;line-height:1.7;color:var(--ink);}
.tc-list{margin:.8rem 0 0;padding-left:1.1rem;color:#5A4651;font-size:.92rem;line-height:1.65;}
.tc-note{margin-top:.9rem;font-size:.82rem;color:var(--muted);line-height:1.5;}
.tc-chip{display:inline-block;margin:.3rem .3rem 0 0;padding:.22rem .7rem;border-radius:999px;background:var(--pink-soft);color:var(--pink-dark);font-size:.78rem;font-weight:500;}
.tc-h{font-size:.74rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 .5rem;}
.tc-src{padding:.8rem 0;border-bottom:1px solid #F8E8EF;}
.tc-src:last-child{border-bottom:none;padding-bottom:0;}
.tc-src a{color:var(--ink);font-weight:600;text-decoration:none;font-size:.93rem;line-height:1.4;}
.tc-src a:hover{color:var(--pink-dark);}
.tc-src small{display:block;color:var(--muted);margin-top:.2rem;font-size:.8rem;line-height:1.5;}
.tc-ok{display:inline-block;margin-left:.5rem;padding:.05rem .55rem;border-radius:999px;background:#E7F6EF;color:#2F9E75;font-size:.7rem;font-weight:600;vertical-align:middle;}
.tc-kv{display:grid;grid-template-columns:96px 1fr;gap:.45rem 1rem;font-size:.9rem;line-height:1.55;}
.tc-kv span:nth-child(odd){color:var(--muted);}
"""
st.markdown("<style>" + THEME_CSS + "</style>", unsafe_allow_html=True)
st.markdown(
    '<div class="tc-hero"><span class="tc-badge">TRUTHCHECK</span>'
    "<h1>Is it real?</h1>"
    "<p>Paste a headline or upload a screenshot. We check it against fact-checkers and credible news.</p></div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("**Status**")
    st.caption(f"Groq key: {'loaded' if GROQ_API_KEY else 'missing'}")
    st.caption(f"Fact Check key: {'loaded' if FACT_CHECK_KEY else 'missing (registry skipped)'}")

if not GROQ_API_KEY:
    st.error("Missing GROQ_API_KEY. Add it to .streamlit/secrets.toml or an environment variable.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)


# --- 2. HELPERS ---
def parse_json(raw: str) -> dict:
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)  # reasoning models
    try:
        return json.loads(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return {}


TEXT_MODEL_PREFS = [
    TEXT_MODEL,
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "llama-3.1-8b-instant",
]


@st.cache_data(ttl=600, show_spinner=False)
def list_available_models() -> list:
    try:
        return sorted(m.id for m in client.models.list().data)
    except Exception:
        return []


def pick_text_models() -> list:
    """Preferred text models that this API key can actually use, in order."""
    available = list_available_models()
    if not available:
        return TEXT_MODEL_PREFS  # could not list, so just try them in order
    return [m for m in TEXT_MODEL_PREFS if m in available]


def llm_json(prompt: str, model: str = None) -> dict:
    models = [model] if model else pick_text_models()
    if not models:
        raise RuntimeError(
            "None of the supported text models are enabled for this Groq key. "
            f"Models your key can use: {list_available_models()}. "
            "Check Model Permissions in your Groq console (Settings > Limits)."
        )
    last_err = None
    for m in models:
        for json_mode in (True, False):
            try:
                kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
                res = client.chat.completions.create(
                    model=m,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    **kwargs,
                )
                data = parse_json(res.choices[0].message.content)
                if data:
                    return data
            except Exception as e:
                last_err = e
                if "model_not_found" in str(e) or "404" in str(e):
                    break  # try the next model
    if last_err:
        raise last_err
    return {}


def tokens(text: str) -> set:
    return set(re.findall(r"\w{4,}", (text or "").lower()))


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def is_credible(url: str) -> bool:
    host = (urlparse(url or "").netloc or "").lower().replace("www.", "")
    return any(host == d or host.endswith("." + d) for d in CREDIBLE_DOMAINS)


def clean_text(text: str) -> str:
    """Strip copy-paste noise (markdown links, URLs, 'Share:' lines) that hurts searching."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"(?im)^\s*(share|advertisement|related|read more)\s*:?\s*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_headline(text: str) -> str:
    """First line that looks like a headline (5 to 30 words), skipping category labels."""
    for line in text.splitlines():
        line = line.strip(" *#>")
        if 5 <= len(line.split()) <= 30:
            return line
    return ""


def detect_outlet(text: str):
    lower = text.lower()
    for name, domain in OUTLETS.items():
        if re.search(r"\b" + re.escape(name) + r"\b", lower):
            return name, domain
    return "", ""


def looks_like_news(text: str) -> bool:
    """Byline ('By: Name Surname') or dateline ('MANILA, Philippines—') present."""
    byline = re.search(r"(?i)\bby:?\s+[A-Z][\w.\-]+\s+\w+", text)
    dateline = re.search(r"\b[A-Z]{3,}[A-Z ]*,\s*[A-Z][a-z]+\s*[—–-]", text)
    return bool(byline or dateline)


# --- 3. SCREENSHOT UNDERSTANDING (vision) ---
def analyze_screenshot(image_bytes: bytes, mime: str):
    """Extract the post text AND the context needed to judge a social media screenshot."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    prompt = """You are examining a screenshot of a social media post or news graphic.
Return ONLY a JSON object with these keys:
{
  "platform": "Facebook/X/Instagram/TikTok/news site/unknown",
  "account_name": "page or profile name as shown, or empty",
  "handle": "username or URL shown, or empty",
  "verified_badge": true or false,
  "date_shown": "date/time shown, or empty",
  "post_text": "ALL headline/caption/body text, verbatim, in the original language",
  "visual_anomalies": ["list only anomalies you actually see, e.g. mismatched fonts, uneven spacing or alignment, logo and page name that do not match, cropped or missing timestamp, missing engagement counts, pixelation around text, unusual layout for this platform"]
}
Do not guess. Use empty values when something is not visible."""
    errors = []
    try:
        available = {m.id for m in client.models.list().data}
    except Exception:
        available = set()
    candidates = [m for m in VISION_MODELS if not available or m in available]
    if not candidates:
        errors.append("None of the configured vision models are available to this API key. "
                      f"Models your key can use: {sorted(available)}")
    for model in candidates:
        try:
            res = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ]}],
                temperature=0.0,
            )
            data = parse_json(res.choices[0].message.content)
            if data.get("post_text"):
                return data, errors
            errors.append(f"{model}: no text found")
        except Exception as e:
            errors.append(f"{model}: {e}")
    return {}, errors


# --- 4. SEARCH QUERY GENERATION ---
def generate_search_queries(text: str) -> list:
    prompt = f"""Create 3 short web search queries to verify this claim.
1. Core named entities plus the action (3-6 words)
2. The central claim in plain English (translate if needed)
3. The claim plus the words "fact check" or "hoax"
Return ONLY JSON: {{"queries": ["...", "...", "..."]}}

Claim:
{text[:1500]}"""
    try:
        qs = llm_json(prompt).get("queries", [])
        qs = [str(q).strip() for q in qs if str(q).strip()]
        if qs:
            return qs[:3]
    except Exception:
        pass
    return [" ".join(text.split()[:10])]


# --- 5. EVIDENCE RETRIEVAL ---
def check_fact_check_registry(queries: list):
    if not FACT_CHECK_KEY:
        return [], ["Fact Check API key missing"]
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    claims, seen, errors = [], set(), []
    for q in queries:
        try:
            res = requests.get(url, params={"query": q, "key": FACT_CHECK_KEY, "pageSize": 10}, timeout=8)
            if res.status_code != 200:
                errors.append(f"Fact Check API {res.status_code}: {res.text[:120]}")
                continue
            for c in res.json().get("claims", []):
                key = c.get("text", "")
                if key not in seen:
                    seen.add(key)
                    claims.append(c)
        except Exception as e:
            errors.append(f"Fact Check API error: {e}")
    return claims, errors


def flag_result(item: dict, claim: str) -> dict:
    blob = f"{item.get('title', '')} {item.get('body', '')}"
    # For news feeds the publisher's own site is what decides credibility
    item["credible"] = is_credible(item.get("publisher_url") or item.get("href"))
    need = min(3, max(1, len(tokens(claim))))
    item["relevant"] = len(tokens(claim) & tokens(blob)) >= need and overlap(claim, blob) >= 0.45
    item["debunk"] = any(w in blob.lower() for w in DEBUNK_WORDS)
    item["credible_relevant"] = item["credible"] and item["relevant"] and not item["debunk"]
    return item


def search_live_web(queries: list, claim: str, per_query: int = 6):
    results, seen, errors = [], set(), []
    for q in queries:
        try:
            with DDGS() as ddgs:
                for item in ddgs.text(q, max_results=per_query):
                    href = item.get("href")
                    if href and href not in seen:
                        seen.add(href)
                        item["source_engine"] = "DuckDuckGo"
                        results.append(flag_result(item, claim))
        except Exception as e:
            errors.append(f"DuckDuckGo error for '{q[:60]}': {e}")
    return results, errors


def search_news_feeds(queries: list, claim: str, per_query: int = 8):
    """Google News and Bing News RSS. Better than web search for fresh articles,
    and each item reports its publisher, so credibility is judged on the real outlet."""
    results, seen, errors = [], set(), []
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36"}
    feeds = (
        ("Google News", "https://news.google.com/rss/search",
         lambda q: {"q": q, "hl": "en-PH", "gl": "PH", "ceid": "PH:en"}),
        ("Bing News", "https://www.bing.com/news/search",
         lambda q: {"q": q, "format": "rss"}),
    )
    for q in queries:
        for name, url, make_params in feeds:
            try:
                res = requests.get(url, params=make_params(q), headers=ua, timeout=8)
                if res.status_code != 200:
                    errors.append(f"{name} returned {res.status_code} for '{q[:60]}'")
                    continue
                root = ET.fromstring(res.content)
                for it in list(root.iter("item"))[:per_query]:
                    link = (it.findtext("link") or "").strip()
                    src = it.find("source")
                    publisher = src.get("url") if src is not None else ""
                    if not link or link in seen:
                        continue
                    seen.add(link)
                    item = {"title": (it.findtext("title") or "").strip(), "href": link,
                            "publisher_url": publisher, "source_engine": name,
                            "body": re.sub(r"<[^>]+>", " ", it.findtext("description") or "")[:240]}
                    results.append(flag_result(item, claim))
            except Exception as e:
                errors.append(f"{name} error for '{q[:60]}': {e}")
    return results, errors


def gather_web(queries: list, extra: list, headline: str, claim_key: str, max_total: int = 16):
    feed_queries = ([headline[:120]] if headline else []) + queries[:2]
    feed_results, feed_err = search_news_feeds(feed_queries, claim_key)
    web_results, web_err = search_live_web(queries + extra, claim_key)
    merged, seen = [], set()
    for r in feed_results + web_results:
        if r.get("href") not in seen:
            seen.add(r.get("href"))
            merged.append(r)
    # Credible sources that match the claim first, so the judge sees them
    merged.sort(key=lambda r: (not r["credible_relevant"], not r["credible"]))
    return merged[:max_total], feed_err + web_err


def registry_signal(claim_text: str, registry: list):
    """Return (relevant_negative, relevant_positive, relevant_items)."""
    neg = pos = False
    relevant = []
    a = tokens(claim_text)
    for c in registry:
        b = tokens(c.get("text", ""))
        shared = a & b
        # Must be the SAME claim: several shared words and a high share of all words.
        # (Short unrelated fact-checks used to match long claims by accident.)
        if len(shared) < 3 or len(shared) / max(1, len(a | b)) < 0.4:
            continue
        relevant.append(c)
        for r in c.get("claimReview", []):
            rating = (r.get("textualRating") or "").lower()
            if any(w in rating for w in NEGATIVE_RATINGS):
                neg = True
            elif any(w in rating for w in POSITIVE_RATINGS):
                pos = True
    return neg, pos, relevant


# --- 6. RED-FLAG ANALYSIS (content-level signals) ---
def scan_red_flags(text: str, screenshot: dict) -> dict:
    context = ""
    if screenshot:
        context = f"\nScreenshot context: {json.dumps(screenshot, ensure_ascii=False)[:1200]}"
    prompt = f"""Assess how many misinformation warning signs this text has. Look for:
- scam patterns: free cash or prizes, links or forms to claim, "ayuda" offers, requests for personal data
- pressure to share urgently ("share before it is deleted", "forward to 10 people")
- sensational or emotional language, ALL CAPS, excessive punctuation
- no named, checkable source or official reference
- implausible, absolute or conspiratorial claims (miracle cures, secret cover-ups)
- impersonation cues (page name does not match the claimed outlet or agency)
- fabricated-looking specifics (arrest warrants, quotes with no source)
Signs of genuine reporting LOWER the risk: an outlet name, byline, dateline, named officials, and
specific checkable details such as court names, dates, or case identifiers. A serious, political, or
crime-related topic is NOT a red flag by itself. Do not penalize a text for describing recent events.
Return ONLY JSON: {{"risk_score": 0-100, "flags": ["short phrases of flags actually present"]}}

Text:
{text[:2000]}{context}"""
    try:
        data = llm_json(prompt)
        return {"risk_score": int(data.get("risk_score", 0)), "flags": data.get("flags", [])}
    except Exception:
        return {"risk_score": 0, "flags": []}


# --- 7. FINAL JUDGMENT ---
def build_evidence(registry, web, flags, screenshot, source_note: str = "") -> str:
    parts = []
    if source_note:
        parts.append(f"=== TEXT FORM ===\n{source_note}")
    if registry:
        parts.append("=== FACT-CHECK REGISTRY ===")
        for c in registry[:4]:
            for r in c.get("claimReview", [])[:2]:
                parts.append(f"- Claim: {c.get('text')} | {r.get('publisher', {}).get('name')}: "
                             f"{r.get('textualRating')} | {r.get('url')}")
    if web:
        parts.append("=== WEB RESULTS (credible = known news/government/fact-check domain) ===")
        for s in web[:10]:
            tag = ("CREDIBLE, matches claim" if s.get("credible_relevant")
                   else "CREDIBLE, weak match" if s.get("credible") else "unrated")
            if s.get("debunk"):
                tag += ", contains debunk wording"
            parts.append(f"- [{tag}] {s.get('title')} ({s.get('href')}): {(s.get('body') or '')[:240]}")
    parts.append(f"=== RED FLAGS === risk {flags['risk_score']}/100: {flags['flags']}")
    if screenshot:
        parts.append("=== SCREENSHOT CONTEXT ===\n" + json.dumps(screenshot, ensure_ascii=False)[:1200])
    return "\n".join(parts)


def judge(claim: str, evidence: str) -> dict:
    prompt = f"""You are a rigorous fact-checker. Today is {date.today().isoformat()}.
Classify the claim as TRUE, FALSE, MISLEADING, or UNVERIFIED.

Rules:
1. Weigh the supplied evidence first, then well-established knowledge. Your own knowledge may be outdated, so recent claims need corroboration in the evidence.
2. TRUE: corroborated by credible sources or an official agency, and nothing in the evidence contradicts it.
3. FALSE: contradicted by credible sources or a fact-check, OR it shows strong scam or fabrication red flags and no credible source supports it.
4. MISLEADING: partly true, but exaggerated, missing context, outdated, or wrongly attributed.
5. UNVERIFIED: only for neutral, plausible, low-risk claims that simply lack evidence. Never use it for a claim with strong red flags.
6. Missing search results are weak evidence, not proof of falsehood. Unrelated results do not support the claim.
7. Judge the claim, not the writing style alone.
8. Your training knowledge ends before today. Never call a claim fabricated just because you do not recognize the event. For recent events, rely only on the evidence above.
9. One or more results marked "CREDIBLE, matches claim" is strong support for TRUE. Do not answer UNVERIFIED when such a result exists, unless it contradicts the claim or only matches a small part of it.
10. A news-style layout, byline, or outlet name inside the pasted text is not proof by itself, since anyone can copy a format. Treat it as a reason to look for the story at that outlet, not as confirmation.

CLAIM:
\"\"\"{claim[:2500]}\"\"\"

EVIDENCE:
{evidence}

Return ONLY JSON:
{{"verdict": "TRUE|FALSE|MISLEADING|UNVERIFIED",
  "confidence": integer 0-100 (your confidence in THIS verdict),
  "explanation": "2-3 factual sentences citing the evidence",
  "key_reasons": ["up to 3 short bullet reasons"]}}"""
    return llm_json(prompt)


def apply_guards(result: dict, reg_neg: bool, reg_pos: bool, web: list, risk: int,
                 news_structure: bool = False) -> dict:
    """Deterministic checks so the model cannot drift from the hard evidence."""
    verdict = str(result.get("verdict", "UNVERIFIED")).upper()
    supported = sum(1 for s in web if s.get("credible_relevant"))
    debunked = sum(1 for s in web if s.get("credible") and s.get("relevant") and s.get("debunk"))
    note = None
    conf_floor = 70

    if reg_neg and verdict != "FALSE":
        verdict, note = "FALSE", "A matching claim was rated false or misleading by a fact-checker."
    elif supported >= 1 and not debunked and verdict in ("FALSE", "UNVERIFIED") and risk < 60:
        verdict = "TRUE"
        note = f"{supported} credible source(s) report the same story."
        conf_floor = 75 if supported == 1 else 88
    elif supported == 0 and risk >= 80 and not news_structure and verdict in ("TRUE", "UNVERIFIED"):
        verdict, note = "FALSE", "Very high-risk claim with no credible source supporting it."
    elif verdict == "FALSE" and supported == 0 and news_structure and not reg_neg and risk < 80:
        verdict, note = "UNVERIFIED", ("Reads like a news article but no matching coverage was found. "
                                       "That is not proof it is fake. Check the outlet's own site.")
    elif verdict == "TRUE" and supported == 0 and not reg_pos and risk >= 40:
        verdict, note = "UNVERIFIED", "No credible corroboration found for a claim with warning signs."

    result["verdict"] = verdict
    if note:
        result["guard_note"] = note
        if verdict in ("TRUE", "FALSE"):
            result["confidence"] = max(int(result.get("confidence", 60)), conf_floor)
    return result


# --- 8. UI HELPERS ---
def esc(x) -> str:
    """HTML-escape and collapse whitespace so text is safe inside one-line HTML cards."""
    return html.escape(" ".join(str(x if x is not None else "").split()), quote=True)


def safe_url(u) -> str:
    u = str(u or "")
    return html.escape(u, quote=True) if u.startswith(("http://", "https://")) else "#"


VERDICT_STYLE = {
    "TRUE": ("Likely true", "#2F9E75"),
    "FALSE": ("Likely false", "#D6336C"),
    "MISLEADING": ("Misleading", "#D98A14"),
    "UNVERIFIED": ("Unverified", "#8F7A86"),
}


def verdict_card(result: dict, conf: int, flags: dict, screenshot: dict) -> str:
    verdict = str(result.get("verdict", "UNVERIFIED")).upper()
    label, color = VERDICT_STYLE.get(verdict, VERDICT_STYLE["UNVERIFIED"])
    reasons = "".join(f"<li>{esc(r)}</li>" for r in (result.get("key_reasons") or []))
    reasons_html = f'<ul class="tc-list">{reasons}</ul>' if reasons else ""
    chips = "".join(f'<span class="tc-chip">{esc(f)}</span>' for f in (flags.get("flags") or [])[:6])
    chips_html = f'<div class="tc-note">Warning signs noticed</div><div>{chips}</div>' if chips else ""
    notes = []
    if result.get("guard_note"):
        notes.append(esc(result["guard_note"]))
    if screenshot:
        notes.append("A screenshot cannot be authenticated by itself. Open the original post or the "
                     "outlet's own page to confirm it exists.")
    notes_html = "".join(f'<div class="tc-note">{n}</div>' for n in notes)
    return (
        '<div class="tc-card">'
        f'<div class="tc-verdict"><span class="tc-dot" style="background:{color}"></span>'
        f'<span class="tc-label" style="color:{color}">{label}</span>'
        f'<span class="tc-conf">{conf}% confidence</span></div>'
        f'<div class="tc-bar"><div style="width:{conf}%;background:{color}"></div></div>'
        f'<div class="tc-text">{esc(result.get("explanation", ""))}</div>'
        f"{reasons_html}{chips_html}{notes_html}</div>"
    )


def screenshot_card(screenshot: dict, claim: str) -> str:
    rows = [
        ("Platform", screenshot.get("platform") or "unknown"),
        ("Account", f"{screenshot.get('account_name') or 'n/a'} {screenshot.get('handle') or ''}"),
        ("Date shown", screenshot.get("date_shown") or "n/a"),
        ("Text", claim),
    ]
    kv = "".join(f"<span>{esc(k)}</span><span>{esc(v)}</span>" for k, v in rows)
    chips = "".join(f'<span class="tc-chip">{esc(a)}</span>'
                    for a in (screenshot.get("visual_anomalies") or [])[:6])
    chips_html = f'<div class="tc-note">Possible edits</div><div>{chips}</div>' if chips else ""
    return (f'<div class="tc-card"><div class="tc-h">Read from screenshot</div>'
            f'<div class="tc-kv">{kv}</div>{chips_html}</div>')


def registry_html(items: list) -> str:
    rows = []
    for c in items[:3]:
        for r in c.get("claimReview", []):
            name = esc(r.get("publisher", {}).get("name"))
            rating = esc(r.get("textualRating"))
            rows.append(
                f'<div class="tc-src"><a href="{safe_url(r.get("url"))}" target="_blank" rel="noopener">'
                f"{name}: {rating}</a><small>Audited claim: {esc(c.get('text'))}</small></div>")
    return '<div class="tc-card"><div class="tc-h">Fact-check matches</div>' + "".join(rows) + "</div>"


def sources_html(web: list) -> str:
    rows = []
    for s in web[:8]:
        badge = '<span class="tc-ok">credible</span>' if s.get("credible") else ""
        body = esc((s.get("body") or "")[:160])
        small = f"<small>{body}</small>" if body else ""
        rows.append(
            f'<div class="tc-src"><a href="{safe_url(s.get("href"))}" target="_blank" rel="noopener">'
            f'{esc(s.get("title"))}</a>{badge}{small}</div>')
    return '<div class="tc-card"><div class="tc-h">Sources found</div>' + "".join(rows) + "</div>"


# --- 9. INPUT UI ---
tab_text, tab_img = st.tabs(["Text or headline", "Screenshot"])

with tab_text:
    input_text = st.text_area("Claim", height=170, key="txt_input", label_visibility="collapsed",
                              placeholder="Paste a headline or article here...")

with tab_img:
    uploaded_file = st.file_uploader("Screenshot", type=["png", "jpg", "jpeg", "webp"],
                                     key="img_uploader", label_visibility="collapsed")
    if uploaded_file is not None:
        st.image(uploaded_file, use_container_width=True)


# --- 10. PIPELINE ---
if st.button("Check authenticity", use_container_width=True):
    diagnostics = []
    screenshot = {}
    claim = input_text.strip()

    try:
        if uploaded_file is not None and not claim:
            with st.spinner("Reading screenshot..."):
                screenshot, ocr_errors = analyze_screenshot(
                    uploaded_file.getvalue(), uploaded_file.type or "image/jpeg")
                diagnostics += ocr_errors
                claim = (screenshot.get("post_text") or "").strip()
            if screenshot:
                st.markdown(screenshot_card(screenshot, claim), unsafe_allow_html=True)

        if not claim:
            st.warning("Provide text, or upload a readable screenshot.")
            if diagnostics:
                st.caption(" | ".join(diagnostics))
            st.stop()

        with st.spinner("Checking sources..."):
            claim = clean_text(claim)
            outlet_name, outlet_domain = detect_outlet(claim)
            headline = extract_headline(claim)
            news_structure = looks_like_news(claim)

            queries = generate_search_queries(claim)
            extra = []
            if headline:
                extra.append(f'"{headline[:120]}"')
                if outlet_domain:
                    extra.append(f"{headline[:120]} site:{outlet_domain}")
            registry, reg_err = check_fact_check_registry(queries)
            web, web_err = gather_web(queries, extra, headline, headline or claim)
            queries = queries + extra
            diagnostics += reg_err + web_err

            reg_neg, reg_pos, relevant_registry = registry_signal(headline or claim[:300], registry)
            flags = scan_red_flags(claim, screenshot)
            if screenshot.get("visual_anomalies"):
                flags["risk_score"] = min(100, flags["risk_score"] + 10)

            notes = []
            if news_structure:
                notes.append("Text has news-article structure (byline or dateline).")
            if outlet_name:
                notes.append(f"Text names the outlet '{outlet_name}'.")
            source_note = " ".join(notes)

            evidence = build_evidence(relevant_registry, web, flags, screenshot, source_note)
            result = judge(claim, evidence)
            raw_verdict = str(result.get("verdict"))
            result = apply_guards(result, reg_neg, reg_pos, web, flags["risk_score"], news_structure)
            diagnostics.append(
                f"DEBUG | model said: {raw_verdict} | final: {result.get('verdict')} | "
                f"risk: {flags['risk_score']} | registry negative: {reg_neg} | "
                f"registry matches: {len(relevant_registry)} | web results: {len(web)} | "
                f"credible matching sources: {sum(1 for s in web if s.get('credible_relevant'))} | "
                f"news structure: {news_structure}")

        conf = max(0, min(100, int(result.get("confidence", 50))))

        st.markdown(verdict_card(result, conf, flags, screenshot), unsafe_allow_html=True)
        if relevant_registry:
            st.markdown(registry_html(relevant_registry), unsafe_allow_html=True)
        if web:
            st.markdown(sources_html(web), unsafe_allow_html=True)

        with st.expander("Search details"):
            st.caption("Search queries: " + " | ".join(queries))
            for d in diagnostics:
                st.write(d)

    except Exception as e:
        st.error(f"Execution error: {e}")