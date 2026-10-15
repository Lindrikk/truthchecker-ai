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
st.set_page_config(page_title="TruthCheck", page_icon="✅", layout="wide",
                   initial_sidebar_state="collapsed")


def get_secret(name: str) -> str:
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, "")


GROQ_API_KEY = get_secret("GROQ_API_KEY")
FACT_CHECK_KEY = get_secret("GOOGLE_FACT_CHECK_API_KEY")

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
@import url('https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700;800&display=swap');
@property --n{syntax:'<integer>';inherits:false;initial-value:0;}
:root{
  /* Palette: "Forest and lime" from taste-skill. Lime marks the action and the progress track only. */
  --bg:#0f1f10;--surface:#162a17;--surface-2:#1e3720;--ink:#ffffff;--muted:#a3ada3;
  --accent:#c6f19d;--accent-strong:#dcf9bf;--accent-ink:#0f1f10;
  --true:#8fe0a4;--false:#ff8a75;--mislead:#f5c451;--unver:#a3ada3;
  --font:'Schibsted Grotesk',system-ui,-apple-system,sans-serif;
  --ease-out:cubic-bezier(.22,1,.36,1);--ease-soft:cubic-bezier(.33,1,.68,1);
  --t-press:140ms;--t-hover:180ms;--t-reveal:800ms;
  --gutter:clamp(1rem,4vw,3rem);
}
.stApp{background:var(--bg);color:var(--ink);font-family:var(--font);}
.stApp :is(p,li,label,textarea,button,h1,h2,h3,div,small,a,dt,dd,b){font-family:var(--font);}
#MainMenu,footer,header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none !important;}
[data-testid="stMain"]{overflow-x:clip;}
.block-container{max-width:1280px;padding:1.5rem var(--gutter) 3rem;}
::selection{background:var(--accent);color:var(--accent-ink);}
[data-testid="stHeaderActionElements"]{display:none !important;}

/* Top bar: wordmark and one link */
.tc-top{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;margin:0 0 clamp(2.5rem,9vh,5.5rem);}
.tc-wordmark{font-size:1.2rem;font-weight:800;letter-spacing:-.03em;color:var(--ink);}
.tc-top a{color:var(--ink) !important;font-weight:600;font-size:1rem;text-decoration:underline;text-decoration-color:transparent;
  text-underline-offset:.25em;transition:text-decoration-color var(--t-hover) ease;}
.tc-top a:hover{text-decoration-color:var(--accent);}

/* The question, as wide as the page allows */
.tc-hero h1{font-size:clamp(5rem,21.5vw,21rem);font-weight:800;letter-spacing:-.055em;line-height:.86;margin:0 0 clamp(2rem,5vh,3.5rem);padding:0;color:var(--ink);}
.tc-lines .line{display:inline-block;overflow:hidden;padding-bottom:.08em;margin-bottom:-.08em;vertical-align:bottom;}
.tc-lines .line:first-child{margin-right:.22em;}
.tc-lines .line>span{display:block;}
@media (max-width:760px){.tc-lines .line{display:block;margin-right:0;}.tc-hero h1{font-size:clamp(5rem,23vw,9rem);}}
.tc-lede{font-size:clamp(1.2rem,1.7vw,1.5rem);line-height:1.45;color:var(--ink);margin:0 0 1.75rem;max-width:36ch;letter-spacing:-.01em;}

/* Columns */
[data-testid="stHorizontalBlock"]{gap:clamp(1.5rem,4vw,4rem) !important;}

/* Tabs */
[data-testid="stTabs"] [role="tablist"]{gap:2rem;background:transparent;height:3rem;}
[data-testid="stTabs"] [role="tablist"]::after{display:none;}
[data-testid="stTab"]{height:3rem;padding:0;background:transparent;color:var(--muted);transition:color var(--t-hover) ease;}
[data-testid="stTab"] p{font-size:1.1rem;font-weight:600;color:inherit;}
[data-testid="stTab"]:hover{color:var(--ink);}
[data-testid="stTab"][aria-selected="true"]{color:var(--ink) !important;}
[data-testid="stTab"] [class*="SelectionIndicator"]{background-color:var(--accent) !important;height:3px;}
[data-testid="stTabPanel"]{padding-top:1rem;}

/* Inputs */
[data-testid="stTextAreaRootElement"]{background:var(--surface) !important;border:none !important;border-radius:0 !important;
  transition:background-color var(--t-hover) ease;}
[data-testid="stTextAreaRootElement"]:hover{background:var(--surface-2) !important;}
[data-testid="stTextAreaRootElement"]:focus-within{outline:2px solid var(--accent);outline-offset:0;}
.stTextArea textarea{background:transparent;color:var(--ink);font-size:1.08rem;padding:1.25rem;line-height:1.6;caret-color:var(--accent);}
.stTextArea textarea::placeholder{color:var(--muted);opacity:1;}
[data-testid="stFileUploaderDropzone"]{background:var(--surface);border:none;border-radius:0;padding:2.25rem 1.5rem;transition:background-color var(--t-hover) ease;}
[data-testid="stFileUploaderDropzone"]:hover{background:var(--surface-2);}
[data-testid="stFileUploaderDropzone"] button{border-radius:0;border:none;background:var(--surface-2);color:var(--ink);}
[data-testid="stFileUploaderDropzone"]:hover button{background:var(--bg);}

/* Buttons. Base = the example rows; .st-key-run = the one lime action */
.stButton>button{border:none;border-radius:0;transition:transform var(--t-press) var(--ease-out),background-color var(--t-hover) ease,color var(--t-hover) ease;}
.stButton>button:active{transform:scale(.985);}
.stButton>button:focus-visible{outline:2px solid var(--accent);outline-offset:3px;}
.stButton>button:focus:not(:active){border:none;box-shadow:none;}
.st-key-run button{background:var(--accent);color:var(--accent-ink);min-height:3.8rem;padding:1rem 1.6rem;margin-top:.5rem;}
.st-key-run button p{color:var(--accent-ink);font-size:1.15rem;font-weight:700;letter-spacing:-.01em;}
.st-key-run button:hover,.st-key-run button:active,.st-key-run button:focus:not(:active){background:var(--accent-strong);color:var(--accent-ink);}
[class*="st-key-ex_"] button{background:var(--surface);color:var(--ink);min-height:0;padding:1rem 1.15rem;justify-content:flex-start;text-align:left;}
[class*="st-key-ex_"] button > div,[class*="st-key-ex_"] button [data-testid="stMarkdownContainer"]{justify-content:flex-start;text-align:left;width:100%;}
[class*="st-key-ex_"] button p{font-size:1rem;font-weight:500;line-height:1.45;text-align:left;color:var(--ink);white-space:normal;overflow:visible;text-overflow:clip;}
[class*="st-key-ex_"] button *{white-space:normal !important;overflow:visible !important;text-overflow:clip !important;}
[class*="st-key-ex_"] button:hover{background:var(--surface-2);color:var(--ink);}
[class*="st-key-ex_"] button:hover p{color:var(--ink);}
[class*="st-key-ex_"]{margin-bottom:-.35rem;}

/* Side column */
.tc-side-h{font-size:1.35rem;font-weight:700;letter-spacing:-.02em;color:var(--ink);margin:.6rem 0 .3rem;}
.tc-side-p{color:var(--muted);font-size:.98rem;line-height:1.5;margin:0 0 1rem;}
.tc-guide{margin:2.4rem 0 0;}
.tc-guide dl{display:grid;grid-template-columns:auto 1fr;gap:1rem 1rem;margin:1rem 0 0;}
.tc-guide dt{display:flex;align-items:center;gap:.6rem;font-weight:700;font-size:1.05rem;white-space:nowrap;}
.tc-guide dt::before{content:"";width:.8rem;height:.8rem;background:var(--c);flex:none;}
.tc-guide dd{margin:0;font-size:1rem;line-height:1.5;color:var(--ink);}

[data-testid="stExpander"]{margin-top:1.25rem;}
[data-testid="stExpander"] details{border:none;border-radius:0;background:var(--surface);}
[data-testid="stExpander"] summary{color:var(--muted);transition:color var(--t-hover) ease;}
[data-testid="stExpander"] summary:hover{color:var(--ink);}
[data-testid="stAlert"]{border-radius:0;}
[data-testid="stImage"] img{border-radius:0;}
[data-testid="stSpinner"] p{color:var(--muted);font-size:1rem;}

/* Results */
.tc-card{background:var(--surface);padding:clamp(1.5rem,3.5vw,2.4rem);margin:1.25rem 0 0;}
.tc-results-gap{height:clamp(2rem,6vh,3.5rem);}
.tc-label{display:block;overflow:hidden;font-size:clamp(2.8rem,7vw,5.5rem);font-weight:800;letter-spacing:-.05em;line-height:.92;padding-bottom:.08em;margin-bottom:-.08em;}
.tc-label>span{display:block;}
.tc-meter{display:flex;align-items:baseline;gap:.6rem;margin:1.6rem 0 .8rem;}
.tc-num{--n:var(--to);counter-reset:n var(--n);font-size:2.2rem;font-weight:700;letter-spacing:-.03em;font-variant-numeric:tabular-nums;line-height:1;}
.tc-num::before{content:counter(n);}
.tc-num::after{content:"%";}
.tc-meter small{color:var(--muted);font-size:1rem;}
.tc-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}
.tc-bar{height:8px;background:var(--surface-2);margin-bottom:1.8rem;overflow:hidden;}
.tc-bar>div{height:100%;transform-origin:left center;transform:scaleX(var(--w));}
.tc-text{font-size:1.12rem;line-height:1.6;color:var(--ink);}
.tc-list{margin:1.1rem 0 0;padding-left:1.2rem;color:var(--ink);font-size:1rem;line-height:1.6;}
.tc-list li{margin-bottom:.35rem;}
.tc-list li::marker{color:var(--muted);}
.tc-note{margin-top:1.4rem;font-size:.95rem;color:var(--muted);line-height:1.55;}
.tc-chips{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.6rem;}
.tc-chip{display:inline-block;padding:.4rem .75rem;background:var(--surface-2);color:var(--ink);font-size:.92rem;}
.tc-h{font-size:1.35rem;font-weight:700;letter-spacing:-.02em;color:var(--ink);margin:0 0 1rem;}
.tc-src{display:block;padding:1rem 1.1rem;margin:0 -1.1rem;transition:background-color var(--t-hover) ease;}
.tc-src:hover{background:var(--surface-2);}
.tc-src a{color:var(--ink);font-weight:600;text-decoration:underline;text-decoration-color:transparent;text-underline-offset:.2em;
  font-size:1.02rem;line-height:1.4;transition:text-decoration-color var(--t-hover) ease;}
.tc-src a:hover{color:var(--ink);text-decoration-color:var(--accent);}
.tc-src small{display:block;color:var(--muted);margin-top:.3rem;font-size:.92rem;line-height:1.5;}
.tc-ok{display:inline-block;margin-left:.5rem;color:var(--accent);font-size:.88rem;font-weight:600;}
.tc-kv{display:grid;grid-template-columns:110px 1fr;gap:.6rem 1rem;font-size:1rem;line-height:1.55;}
.tc-kv span:nth-child(odd){color:var(--muted);}

/* How a claim is checked: the claim travels a track through six stages */
.tc-how{margin-top:clamp(5rem,14vh,9rem);scroll-margin-top:2rem;}
.tc-how-head{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:clamp(1.5rem,4vw,4rem);align-items:end;margin-bottom:clamp(2.5rem,6vh,4rem);}
.tc-how h2{font-size:clamp(2.6rem,6.5vw,5.6rem);font-weight:800;letter-spacing:-.05em;line-height:.9;margin:0;padding:0;color:var(--ink);}
.tc-how-head p{font-size:1.15rem;line-height:1.5;margin:0;color:var(--ink);max-width:34ch;}
.tc-track{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:0 1.5rem;position:relative;}
.tc-track::before,.tc-track::after{content:"";position:absolute;left:0;right:0;top:0;height:6px;background:var(--surface-2);}
.tc-track::after{background:var(--accent);transform-origin:left center;}
.tc-stage{padding-top:2.4rem;position:relative;}
.tc-stage::before{content:"";position:absolute;top:-5px;left:0;width:16px;height:16px;background:var(--bg);box-shadow:inset 0 0 0 4px var(--accent);z-index:1;}
.tc-big{--n:var(--to);counter-reset:n var(--n);display:block;font-size:clamp(3.4rem,6vw,5.6rem);font-weight:800;letter-spacing:-.05em;line-height:.9;font-variant-numeric:tabular-nums;color:var(--ink);}
.tc-big::before{content:counter(n);}
.tc-stage b{display:block;font-size:1.1rem;font-weight:700;margin:.7rem 0 .5rem;color:var(--ink);}
.tc-stage p{margin:0;font-size:.98rem;line-height:1.5;color:var(--ink);}
.tc-stage small{display:block;margin-top:.6rem;color:var(--muted);font-size:.9rem;}
.tc-out{display:flex;flex-wrap:wrap;align-items:baseline;gap:.5rem 1.25rem;margin-top:clamp(2.5rem,6vh,4rem);padding:1.4rem 1.6rem;background:var(--surface);}
.tc-out b{font-size:1.15rem;}
.tc-out span{display:inline-flex;align-items:center;gap:.45rem;font-weight:600;font-size:1.05rem;}
.tc-out span::before{content:"";width:.75rem;height:.75rem;background:var(--c);}
@media (max-width:980px){
  .tc-track{grid-template-columns:1fr;gap:2.4rem 0;padding-left:2.4rem;}
  .tc-track::before,.tc-track::after{left:5px;right:auto;top:0;bottom:0;width:6px;height:auto;}
  .tc-track::after{transform-origin:center top;}
  .tc-stage{padding-top:0;display:grid;grid-template-columns:minmax(5.5rem,auto) 1fr;column-gap:1.25rem;align-items:start;}
  .tc-stage::before{top:.35rem;left:calc(-2.4rem);}
  .tc-big{grid-row:span 3;font-size:clamp(3.2rem,14vw,4.6rem);}
  .tc-stage b{margin-top:.2rem;}
  .tc-how-head{grid-template-columns:1fr;}
}

/* Close */
.tc-foot{margin-top:clamp(5rem,14vh,9rem);}
.tc-tips{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:clamp(1.5rem,4vw,4rem);}
.tc-tips h2{font-size:clamp(2rem,4vw,3.2rem);font-weight:800;letter-spacing:-.045em;line-height:.95;margin:0;padding:0;color:var(--ink);}
.tc-tips dl{display:grid;grid-template-columns:minmax(0,12rem) 1fr;gap:1.5rem 2rem;margin:0;}
.tc-tips dt{font-weight:700;font-size:1.15rem;color:var(--ink);}
.tc-tips dd{margin:0;font-size:1.08rem;line-height:1.55;color:var(--ink);}
.tc-mark{font-size:clamp(3.4rem,15vw,14rem);font-weight:800;letter-spacing:-.065em;line-height:.78;color:var(--surface-2);margin:clamp(4rem,12vh,7rem) 0 1.4rem -.04em;white-space:nowrap;}
.tc-fine{display:flex;flex-wrap:wrap;justify-content:space-between;gap:.75rem 2rem;color:var(--muted);font-size:.95rem;line-height:1.5;margin:0;}
.tc-fine a{color:var(--ink) !important;}
@media (max-width:760px){
  .tc-tips,.tc-tips dl{grid-template-columns:1fr;}
  .tc-tips dl{gap:.35rem 0;}
  .tc-tips dd{margin-bottom:1.1rem;}
  .tc-kv{grid-template-columns:90px 1fr;}
  .tc-guide dl{grid-template-columns:1fr;gap:.25rem;}
  .tc-guide dd{margin-bottom:.8rem;}
}

/* Motion. Only travel is added here; with reduced motion the page is simply finished. */
@keyframes tc-line{from{transform:translateY(105%);}}
@keyframes tc-rise{from{opacity:0;transform:translateY(22px);}}
@keyframes tc-fill{from{transform:scaleX(0);}}
@keyframes tc-fill-y{from{transform:scaleY(0);}}
@keyframes tc-count{from{--n:0;}}
@keyframes tc-open{from{clip-path:inset(0 0 100% 0);}}
@keyframes tc-mark{from{transform:translateX(4%);opacity:.3;}}
@keyframes tc-stop{from{box-shadow:inset 0 0 0 4px var(--surface-2);}}
@media (prefers-reduced-motion:no-preference){
  /* Signature: the question rises out of its own baseline */
  .tc-lines .line>span{animation:tc-line 1000ms var(--ease-out) both;animation-delay:calc(var(--i)*120ms + 150ms);}
  .tc-top{animation:tc-rise 700ms var(--ease-out) both;}
  .tc-lede{animation:tc-rise var(--t-reveal) var(--ease-out) 450ms both;}
  [data-testid="stTabs"]{animation:tc-rise var(--t-reveal) var(--ease-out) 550ms both;}
  .st-key-run{animation:tc-rise var(--t-reveal) var(--ease-out) 650ms both;}
  .tc-side-h,.tc-side-p{animation:tc-rise var(--t-reveal) var(--ease-out) 600ms both;}
  [class*="st-key-ex_"]{animation:tc-rise 700ms var(--ease-out) both;}
  .st-key-ex_0{animation-delay:680ms;}.st-key-ex_1{animation-delay:750ms;}.st-key-ex_2{animation-delay:820ms;}.st-key-ex_3{animation-delay:890ms;}
  .tc-guide dt,.tc-guide dd{animation:tc-rise 700ms var(--ease-out) both;animation-delay:calc(var(--i,0)*70ms + 950ms);}
  /* The verdict: the panel opens, the word rises, the meter counts and fills */
  .tc-result{animation:tc-open 700ms var(--ease-out) both;}
  .tc-result .tc-label>span{animation:tc-line 900ms var(--ease-out) 200ms both;}
  .tc-result .tc-num{animation:tc-count 1400ms var(--ease-out) 350ms both;}
  .tc-result .tc-bar>div{animation:tc-fill 1400ms var(--ease-out) 350ms both;}
  .tc-result .tc-text{animation:tc-rise 700ms var(--ease-out) 550ms both;}
  .tc-list li,.tc-chip,.tc-src,.tc-kv span{animation:tc-rise 600ms var(--ease-out) both;animation-delay:calc(var(--i,0)*70ms + 600ms);}
  .tc-card:not(.tc-result){animation:tc-rise 700ms var(--ease-out) 250ms both;}
  [data-testid="stImage"]{animation:tc-open 900ms var(--ease-out) both;}
  /* Scroll-driven: the track fills, each stage lights up and counts as it arrives */
  @supports (animation-timeline:view()){
    .tc-how-head>*,.tc-tips h2,.tc-tips dt,.tc-tips dd,.tc-out{animation:tc-rise linear both;animation-timeline:view();animation-range:entry 0% entry 70%;}
    .tc-track{view-timeline-name:--track;}
    .tc-track::after{animation:tc-fill linear both;animation-timeline:--track;animation-range:entry 40% contain 40%;}
    .tc-stage{animation:tc-rise linear both;animation-timeline:view();animation-range:entry 10% entry 90%;}
    .tc-stage::before{animation:tc-stop linear both;animation-timeline:view();animation-range:entry 60% entry 100%;}
    .tc-big{animation:tc-count linear both;animation-timeline:view();animation-range:entry 20% cover 45%;}
    .tc-mark{animation:tc-mark linear both;animation-timeline:view();animation-range:entry 0% entry 100%;}
  }
}
@media (prefers-reduced-motion:no-preference) and (max-width:980px){
  @supports (animation-timeline:view()){
    .tc-track::after{animation-name:tc-fill-y;animation-range:entry 0% exit 60%;}
  }
}
"""
st.markdown("<style>" + THEME_CSS + "</style>", unsafe_allow_html=True)
st.markdown(
    '<div class="tc-top"><span class="tc-wordmark">TruthCheck</span>'
    '<a href="#how" target="_self">How it works</a></div>'
    '<div class="tc-hero"><h1 class="tc-lines">'
    '<span class="line"><span style="--i:0">Is it</span></span>'
    '<span class="line"><span style="--i:1">real?</span></span></h1></div>',
    unsafe_allow_html=True,
)
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
                            "body": html.unescape(re.sub(r"<[^>]+>", " ", it.findtext("description") or ""))[:240]}
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
    "TRUE": ("Likely true", "#8FE0A4"),
    "FALSE": ("Likely false", "#FF8A75"),
    "MISLEADING": ("Misleading", "#F5C451"),
    "UNVERIFIED": ("Unverified", "#A3ADA3"),
}


def verdict_card(result: dict, conf: int, flags: dict, screenshot: dict) -> str:
    verdict = str(result.get("verdict", "UNVERIFIED")).upper()
    label, color = VERDICT_STYLE.get(verdict, VERDICT_STYLE["UNVERIFIED"])
    reasons = "".join(f'<li style="--i:{i}">{esc(r)}</li>'
                      for i, r in enumerate(result.get("key_reasons") or []))
    reasons_html = f'<ul class="tc-list">{reasons}</ul>' if reasons else ""
    chips = "".join(f'<span class="tc-chip" style="--i:{i + 3}">{esc(f)}</span>'
                    for i, f in enumerate((flags.get("flags") or [])[:6]))
    chips_html = (f'<div class="tc-note">Warning signs noticed</div><div class="tc-chips">{chips}</div>'
                  if chips else "")
    notes = []
    if result.get("guard_note"):
        notes.append(esc(result["guard_note"]))
    if screenshot:
        notes.append("A screenshot cannot be authenticated by itself. Open the original post or the "
                     "outlet's own page to confirm it exists.")
    notes_html = "".join(f'<div class="tc-note">{n}</div>' for n in notes)
    return (
        '<div class="tc-card tc-result">'
        f'<div class="tc-label" style="color:{color}"><span>{label}</span></div>'
        f'<div class="tc-meter"><span class="tc-num" style="--to:{conf}" aria-hidden="true"></span>'
        f'<small aria-hidden="true">confidence</small><span class="tc-sr">{conf}% confidence</span></div>'
        f'<div class="tc-bar"><div style="--w:{conf / 100:.2f};background:{color}"></div></div>'
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
    kv = "".join(f'<span style="--i:{i}">{esc(k)}</span><span style="--i:{i}">{esc(v)}</span>'
                 for i, (k, v) in enumerate(rows))
    chips = "".join(f'<span class="tc-chip" style="--i:{i + 4}">{esc(a)}</span>'
                    for i, a in enumerate((screenshot.get("visual_anomalies") or [])[:6]))
    chips_html = f'<div class="tc-note">Possible edits</div><div class="tc-chips">{chips}</div>' if chips else ""
    return (f'<div class="tc-card"><div class="tc-h">Read from the screenshot</div>'
            f'<div class="tc-kv">{kv}</div>{chips_html}</div>')


def registry_html(items: list) -> str:
    rows = []
    for c in items[:3]:
        for r in c.get("claimReview", []):
            name = esc(r.get("publisher", {}).get("name"))
            rating = esc(r.get("textualRating"))
            rows.append(
                f'<div class="tc-src" style="--i:{len(rows)}"><a href="{safe_url(r.get("url"))}" '
                f'target="_blank" rel="noopener">{name}: {rating}</a>'
                f"<small>Audited claim: {esc(c.get('text'))}</small></div>")
    return '<div class="tc-card"><div class="tc-h">Fact-checks of this claim</div>' + "".join(rows) + "</div>"


def sources_html(web: list) -> str:
    rows = []
    for i, s in enumerate(web[:8]):
        badge = '<span class="tc-ok">Credible source</span>' if s.get("credible") else ""
        body = (s.get("body") or "").strip()
        headline = (s.get("title") or "").rsplit(" - ", 1)[0].strip()
        if headline and body.startswith(headline[:50]):
            body = ""  # news feeds repeat the headline as the description
        body = esc(body[:160])
        small = f"<small>{body}</small>" if body else ""
        rows.append(
            f'<div class="tc-src" style="--i:{i}"><a href="{safe_url(s.get("href"))}" target="_blank" '
            f'rel="noopener">{esc(s.get("title"))}</a>{badge}{small}</div>')
    return '<div class="tc-card"><div class="tc-h">Where we looked</div>' + "".join(rows) + "</div>"


VERDICT_GUIDE = (
    ("TRUE", "Credible news or an official agency reports the same story."),
    ("FALSE", "A fact-check rates it false, or it shows strong scam signs with nothing credible behind it."),
    ("MISLEADING", "Partly true, but exaggerated, outdated or missing context."),
    ("UNVERIFIED", "Plausible, but no evidence was found either way yet."),
)

STAGES = (
    (1, "Fact-check registry", "Google Fact Check Tools is searched for the same claim, already rated by fact-checkers.",
     "Google Fact Check Tools"),
    (2, "News feeds", "Google News and Bing News are searched for coverage of the story.", "Google News, Bing News"),
    (len(CREDIBLE_DOMAINS), "Credible sites",
     "Results from known news, government and fact-check sites are marked credible.", "Rappler, Inquirer, PNA, DOH…"),
    (3, "Web searches", "DuckDuckGo is searched with three queries written from the claim.", "DuckDuckGo"),
    (7, "Warning signs", "A language model checks for scam offers, pressure to share, missing sources and more.",
     "Llama 3.3 on Groq"),
    (5, "Override rules", "The model gives a verdict, and fixed rules overrule it when the evidence is clear.",
     "Rule-based guards"),
)


def guide_html() -> str:
    rows = "".join(
        f'<dt style="--c:{VERDICT_STYLE[k][1]};--i:{2 * i}">{VERDICT_STYLE[k][0]}</dt>'
        f'<dd style="--i:{2 * i + 1}">{esc(text)}</dd>'
        for i, (k, text) in enumerate(VERDICT_GUIDE))
    return f'<div class="tc-guide"><div class="tc-side-h">What the verdicts mean</div><dl>{rows}</dl></div>'


def render_footer() -> None:
    stages = "".join(
        f'<li class="tc-stage"><span class="tc-big" style="--to:{n}" aria-hidden="true"></span>'
        f'<span class="tc-sr">{n}</span><b>{esc(name)}</b><p>{esc(text)}</p><small>{esc(tool)}</small></li>'
        for n, name, text, tool in STAGES)
    outcomes = "".join(f'<span style="--c:{color}">{label}</span>' for label, color in VERDICT_STYLE.values())
    st.markdown(
        '<section class="tc-how" id="how"><div class="tc-how-head"><h2>How a claim<br>is checked</h2>'
        "<p>Every claim travels the same six stages, in this order, before a verdict comes out "
        "the other end. Most checks take under a minute.</p></div>"
        f'<ol class="tc-track">{stages}</ol>'
        f'<div class="tc-out"><b>Out comes one of four verdicts:</b>{outcomes}</div></section>'
        '<div class="tc-foot"><div class="tc-tips"><h2>Before you<br>share it</h2><dl>'
        "<dt>Find the original</dt><dd>Open the post or the outlet's own website, not a screenshot "
        "of it. Screenshots are easy to edit.</dd>"
        "<dt>Check the date</dt><dd>Old stories get reshared as if they were new, especially after "
        "disasters and during elections.</dd>"
        "<dt>Ask who gains</dt><dd>Offers of free cash that ask for your name, number or GCash "
        "details are almost always scams.</dd></dl></div>"
        '<div class="tc-mark" aria-hidden="true">TruthCheck</div>'
        '<p class="tc-fine"><span>A verdict is a guide, not the final word. Open the original source '
        'before you share anything.</span><a href="#how" target="_self">How it works</a></p></div>',
        unsafe_allow_html=True,
    )


# --- 9. INPUT UI ---
EXAMPLES = (
    "URGENT: DSWD is giving FREE P5,000 ayuda to every family! Click the link and enter your name and "
    "GCash number to claim before it is deleted. Share now!!!",
    "Drinking warm water with lemon every morning cures cancer, doctors don't want you to know this.",
    "Filipino Sign Language was declared the national sign language of the Philippines in 2018.",
)


def use_example(text: str) -> None:
    st.session_state["txt_input"] = text


col_in, col_side = st.columns([7, 5], gap="large")

with col_in:
    st.markdown('<p class="tc-lede">Paste a headline or upload a screenshot. TruthCheck looks for it in '
                "fact-checks and credible news, then tells you how well it holds up.</p>",
                unsafe_allow_html=True)
    tab_text, tab_img = st.tabs(["Text or headline", "Screenshot"])
    with tab_text:
        input_text = st.text_area("Claim", height=200, key="txt_input", label_visibility="collapsed",
                                  placeholder="Paste a headline or article here...")
    with tab_img:
        uploaded_file = st.file_uploader("Screenshot", type=["png", "jpg", "jpeg", "webp"],
                                         key="img_uploader", label_visibility="collapsed")
        if uploaded_file is not None:
            st.image(uploaded_file, width="stretch")
    run_check = st.button("Check authenticity", key="run", width="stretch")

with col_side:
    st.markdown('<div class="tc-side-h">Try an example</div>'
                '<p class="tc-side-p">Click one to put it in the box, then check it.</p>',
                unsafe_allow_html=True)
    for i, text in enumerate(EXAMPLES):
        st.button(f"“{text[:80].rsplit(' ', 1)[0].rstrip(',.!')}…”", key=f"ex_{i}", on_click=use_example, args=(text,), width="stretch")
    st.markdown(guide_html(), unsafe_allow_html=True)


# --- 10. PIPELINE ---
if run_check:
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
            render_footer()
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

        st.markdown('<div class="tc-results-gap"></div>', unsafe_allow_html=True)
        res_main, res_side = st.columns([7, 5], gap="large")
        with res_main:
            st.markdown(verdict_card(result, conf, flags, screenshot), unsafe_allow_html=True)
            with st.expander("Search details"):
                st.caption("Search queries: " + " | ".join(queries))
                for d in diagnostics:
                    st.write(d)
        with res_side:
            if relevant_registry:
                st.markdown(registry_html(relevant_registry), unsafe_allow_html=True)
            if web:
                st.markdown(sources_html(web), unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Execution error: {e}")

render_footer()
