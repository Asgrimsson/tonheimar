
import streamlit as st
import pandas as pd
import random, json, base64, html, re
from pathlib import Path
import requests

st.set_page_config(page_title="Tónheimar | Auðbert Vigfússon", page_icon="🎵", layout="wide", initial_sidebar_state="expanded")

APP_NAME = "Tónheimar"
PERSON_NAME = "Auðbert Vigfússon"
SUBTITLE = "Persónulegur tónlistarvefur fyrir fjölskylduna"

# --- Örugg session_state frumstilling ---
DEFAULT_SESSION_STATE = {
    "current_index": 0,
    "favorites": set(),
    "big_mode": False,
    "active_playlist": "Enginn",
    "autoplay_current": False,
    "inline_player_index": None,
    "youtube_autoplay": False,
    "party_mode": False,
    "tv_mode": False,
    "mascot_line": "Jæja, nú er kominn tími á alvöru nikkustemningu!",
    "memory_mode": False,
    "memory_image_index": 0,
    "memory_text": "Veldu Minningarvélina og leyfðu Tónheimum að velja mynd, lag og stemningu.",
    "radio_audbert": False,
}

for _key, _value in DEFAULT_SESSION_STATE.items():
    if _key not in st.session_state:
        st.session_state[_key] = _value



@st.cache_data
def load_songs():
    return pd.read_csv("songs.csv").fillna("")

@st.cache_data
def load_playlists():
    p = Path("playlists.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

@st.cache_data
def load_media():
    p = Path("media_manifest.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"images": [], "videos": [], "hero_image": "", "nature_covers": []}

def img_to_data_uri(path):
    p = Path(path)
    if not p.exists():
        return ""
    if p.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    elif p.suffix.lower() in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif p.suffix.lower() == ".png":
        mime = "image/png"
    else:
        mime = "application/octet-stream"
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("utf-8")

def safe_text(value):
    return html.escape(str(value))

def safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def extract_drive_id(url):
    if not url:
        return ""
    for pattern in [r"/file/d/([^/]+)", r"[?&]id=([^&]+)"]:
        m = re.search(pattern, str(url))
        if m:
            return m.group(1)
    return ""

def infer_audio_mime(row):
    filename = str(row.get("original_filename", "") or row.get("file_url", "")).lower()
    if filename.endswith(".mp3"):
        return "audio/mpeg"
    if filename.endswith(".m4a"):
        return "audio/mp4"
    if filename.endswith(".ogg"):
        return "audio/ogg"
    return "audio/wav"

def audio_extension(row):
    filename = str(row.get("original_filename", "") or row.get("file_url", "")).lower()
    for ext in [".wav", ".mp3", ".m4a", ".ogg"]:
        if filename.endswith(ext):
            return ext
    return ".wav"

def download_drive_file_to_cache(file_url, row):
    cache_dir = Path("audio_cache")
    cache_dir.mkdir(exist_ok=True)
    file_id = extract_drive_id(file_url)
    if not file_id:
        return None, "Drive ID fannst ekki í slóðinni."
    target = cache_dir / f"{file_id}{audio_extension(row)}"
    if target.exists() and target.stat().st_size > 5000:
        return target, ""
    session = requests.Session()
    params = {"export": "download", "id": file_id}
    try:
        response = session.get("https://drive.google.com/uc", params=params, stream=True, timeout=45)
    except Exception as e:
        return None, f"Náði ekki sambandi við Google Drive: {e}"
    token = None
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            token = value
            break
    if token:
        params["confirm"] = token
        try:
            response = session.get("https://drive.google.com/uc", params=params, stream=True, timeout=45)
        except Exception as e:
            return None, f"Náði ekki að staðfesta Drive niðurhal: {e}"
    if response.status_code != 200:
        return None, f"Google Drive skilaði HTTP {response.status_code}."
    first = b""
    total = 0
    try:
        with open(target, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024*256):
                if chunk:
                    if not first:
                        first = chunk[:500]
                    f.write(chunk)
                    total += len(chunk)
    except Exception as e:
        return None, f"Náði ekki að vista hljóðskrá: {e}"
    if total < 5000:
        target.unlink(missing_ok=True)
        return None, "Hljóðskráin var of lítil eða tóm."
    if first.lstrip().lower().startswith(b"<!doctype html") or b"<html" in first.lower():
        target.unlink(missing_ok=True)
        return None, "Google Drive skilaði vefsíðu í stað hljóðskrár. Stilltu skrána á Anyone with the link → Viewer."
    return target, ""

def get_audio_source_for_song(row):
    file_url = str(row.get("file_url", ""))
    source_type = str(row.get("source_type", ""))
    if file_url.startswith("assets/"):
        p = Path(file_url)
        if p.exists():
            return p, ""
        return None, f"Staðbundin skrá fannst ekki: {file_url}"
    if "drive.google.com" in file_url or source_type == "drive":
        return download_drive_file_to_cache(file_url, row)
    return file_url, ""

def render_reliable_audio(row, autoplay=False):
    source, error = get_audio_source_for_song(row)
    mime = infer_audio_mime(row)
    if source:
        try:
            st.audio(source.read_bytes(), format=mime)
            return True
        except Exception as e:
            st.error(f"Náði ekki að birta hljóðspilara: {e}")
            return False
    st.error(error or "Lagið gat ekki spilast.")
    st.caption("Athugaðu Google Drive: Share → General access → Anyone with the link → Viewer.")
    return False

def inject_css():
    st.markdown("""
    <style>
    :root{
        --green:#1ed760; --gold:#f7c948; --ink:#050505; --panel:#181818;
        --border:rgba(255,255,255,.10); --muted:#b7b7b7;
    }
    .stApp{
        background:
            radial-gradient(circle at top left, rgba(30,215,96,.20), transparent 28rem),
            radial-gradient(circle at top right, rgba(247,201,72,.13), transparent 24rem),
            linear-gradient(180deg, #0a0a0a 0%, #050505 100%);
        color:white;
    }
    section[data-testid="stSidebar"]{
        background:rgba(0,0,0,.72);
        border-right:1px solid var(--border);
    }
    .main .block-container{padding-top:1.15rem;padding-bottom:7.5rem;max-width:1500px;}
    h1,h2,h3,p,label,span,div{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
    
    @keyframes auroraFlow{
        0%{transform:translateX(-20%) rotate(0deg); opacity:.36;}
        50%{transform:translateX(14%) rotate(8deg); opacity:.58;}
        100%{transform:translateX(-20%) rotate(0deg); opacity:.36;}
    }
    @keyframes floaty{
        0%,100%{transform:translateY(0) rotate(-1deg);}
        50%{transform:translateY(-10px) rotate(1.5deg);}
    }
    @keyframes squeezeBox{
        0%,100%{transform:scaleX(1);}
        50%{transform:scaleX(.72);}
    }
    @keyframes noteFly{
        0%{transform:translateY(18px) translateX(0) rotate(0deg); opacity:0;}
        15%{opacity:1;}
        100%{transform:translateY(-105px) translateX(36px) rotate(18deg); opacity:0;}
    }
    @keyframes glowPulse{
        0%,100%{box-shadow:0 26px 80px rgba(0,0,0,.45), 0 0 0 rgba(30,215,96,0);}
        50%{box-shadow:0 30px 95px rgba(0,0,0,.55), 0 0 45px rgba(30,215,96,.25);}
    }
    .hero-wow{
        position:absolute;
        inset:0;
        pointer-events:none;
        overflow:hidden;
    }

    body.party-on .stApp, .party-on{
        background:
            radial-gradient(circle at 10% 10%, rgba(255,0,102,.25), transparent 18rem),
            radial-gradient(circle at 85% 12%, rgba(30,215,96,.26), transparent 20rem),
            radial-gradient(circle at 50% 85%, rgba(247,201,72,.22), transparent 24rem),
            linear-gradient(180deg, #070707 0%, #050505 100%) !important;
    }
    @keyframes partyFlash{
        0%,100%{filter:hue-rotate(0deg) saturate(1);}
        50%{filter:hue-rotate(38deg) saturate(1.35);}
    }
    @keyframes discoPulse{
        0%,100%{transform:scale(1); opacity:.55;}
        50%{transform:scale(1.08); opacity:.95;}
    }
    .party-banner{
        border-radius:30px;
        border:1px solid rgba(247,201,72,.35);
        background:
            radial-gradient(circle at 20% 20%, rgba(247,201,72,.24), transparent 16rem),
            radial-gradient(circle at 80% 10%, rgba(236,72,153,.22), transparent 14rem),
            rgba(255,255,255,.06);
        padding:22px;
        margin:16px 0 22px;
        box-shadow:0 22px 70px rgba(0,0,0,.36), 0 0 40px rgba(247,201,72,.16);
        animation:partyFlash 3.2s ease-in-out infinite;
        position:relative;
        overflow:hidden;
    }
    .party-banner:after{
        content:"";
        position:absolute;
        right:-80px; top:-80px;
        width:220px; height:220px;
        border-radius:999px;
        background:conic-gradient(#facc15,#1ed760,#ec4899,#38bdf8,#facc15);
        filter:blur(14px);
        animation:discoPulse 1.8s ease-in-out infinite;
        opacity:.55;
    }
    .party-banner h2{margin:0 0 8px; font-size:clamp(1.7rem,4vw,3rem);}
    .party-banner p{margin:0; color:#f3f3f3; font-size:1.05rem;}
    .mascot-panel{
        display:grid;
        grid-template-columns:120px minmax(0,1fr);
        gap:16px;
        align-items:center;
        border-radius:28px;
        border:1px solid rgba(30,215,96,.32);
        background:linear-gradient(135deg, rgba(30,215,96,.13), rgba(255,255,255,.045));
        padding:16px;
        margin:14px 0 20px;
        box-shadow:0 18px 50px rgba(0,0,0,.28);
    }
    .mascot-bubble{
        position:relative;
        background:rgba(0,0,0,.30);
        border:1px solid rgba(255,255,255,.12);
        border-radius:22px;
        padding:14px 16px;
        color:#fff;
        font-weight:850;
        line-height:1.4;
    }
    .mascot-bubble:before{
        content:"";
        position:absolute;
        left:-10px;
        top:36px;
        width:20px;height:20px;
        transform:rotate(45deg);
        background:rgba(0,0,0,.30);
        border-left:1px solid rgba(255,255,255,.12);
        border-bottom:1px solid rgba(255,255,255,.12);
    }
    .tv-mode-wrap{
        border-radius:34px;
        border:1px solid rgba(255,255,255,.13);
        background:
            radial-gradient(circle at 50% 15%, rgba(30,215,96,.18), transparent 24rem),
            linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.025));
        padding:26px;
        box-shadow:0 30px 90px rgba(0,0,0,.45);
        margin:16px 0 22px;
    }
    .tv-now{
        display:grid;
        grid-template-columns:minmax(240px, .8fr) minmax(0,1.2fr);
        gap:28px;
        align-items:center;
    }
    .tv-cover{
        border-radius:30px;
        overflow:hidden;
        border:1px solid rgba(255,255,255,.16);
        box-shadow:0 28px 80px rgba(0,0,0,.48);
        min-height:360px;
        background:#111;
    }
    .tv-cover img{width:100%;height:100%;min-height:360px;object-fit:cover;display:block;}
    .tv-title{
        font-size:clamp(2.2rem,6vw,5rem);
        line-height:.95;
        letter-spacing:-.06em;
        font-weight:1000;
        margin-bottom:14px;
    }
    .tv-sub{
        color:#d7d7d7;
        font-size:clamp(1.05rem,2vw,1.35rem);
        margin-bottom:22px;
    }
    .spilarinn-card{
        border-radius:28px;
        border:1px solid rgba(56,189,248,.32);
        background:
            radial-gradient(circle at 14% 18%, rgba(56,189,248,.18), transparent 18rem),
            linear-gradient(135deg, rgba(255,255,255,.08), rgba(255,255,255,.035));
        padding:20px;
        margin:16px 0;
        box-shadow:0 20px 60px rgba(0,0,0,.3);
    }
    .spilarinn-card h3{margin-top:0;}

    .memory-machine{
        position:relative;
        overflow:hidden;
        border-radius:34px;
        border:1px solid rgba(247,201,72,.32);
        background:
            radial-gradient(circle at 18% 18%, rgba(247,201,72,.24), transparent 22rem),
            radial-gradient(circle at 82% 8%, rgba(30,215,96,.23), transparent 22rem),
            linear-gradient(145deg, rgba(255,255,255,.08), rgba(255,255,255,.035));
        padding:24px;
        margin:18px 0 24px;
        box-shadow:0 30px 90px rgba(0,0,0,.44), 0 0 42px rgba(247,201,72,.12);
    }
    .memory-machine:before{
        content:"";
        position:absolute;
        inset:-120px;
        background:conic-gradient(from 45deg, transparent, rgba(247,201,72,.18), transparent, rgba(30,215,96,.14), transparent);
        animation:slowSpin 16s linear infinite;
        pointer-events:none;
    }
    .memory-inner{
        position:relative;
        z-index:1;
        display:grid;
        grid-template-columns:minmax(260px,.9fr) minmax(0,1.1fr);
        gap:24px;
        align-items:center;
    }
    .memory-photo{
        border-radius:28px;
        overflow:hidden;
        min-height:360px;
        background:#111;
        border:1px solid rgba(255,255,255,.16);
        box-shadow:0 24px 70px rgba(0,0,0,.45);
    }
    .memory-photo img{
        width:100%;
        height:100%;
        min-height:360px;
        object-fit:cover;
        display:block;
    }
    .memory-kicker{
        display:inline-flex;
        padding:8px 12px;
        border-radius:999px;
        background:linear-gradient(135deg, rgba(247,201,72,.95), rgba(255,245,180,.95));
        color:#111;
        font-weight:950;
        margin-bottom:12px;
    }
    .memory-title{
        font-size:clamp(2rem,5vw,4.3rem);
        font-weight:1000;
        letter-spacing:-.065em;
        line-height:.94;
        margin-bottom:14px;
        color:#fff;
    }
    .memory-text{
        color:#f2f2f2;
        font-size:1.12rem;
        line-height:1.55;
        background:rgba(0,0,0,.28);
        border:1px solid rgba(255,255,255,.12);
        border-radius:22px;
        padding:16px;
        margin-bottom:14px;
    }
    .radio-panel{
        border-radius:34px;
        border:1px solid rgba(56,189,248,.32);
        background:
            radial-gradient(circle at 18% 18%, rgba(56,189,248,.18), transparent 22rem),
            radial-gradient(circle at 90% 5%, rgba(30,215,96,.20), transparent 20rem),
            rgba(255,255,255,.05);
        padding:22px;
        margin:18px 0 24px;
        box-shadow:0 28px 80px rgba(0,0,0,.38), 0 0 36px rgba(56,189,248,.12);
    }
    .radio-title{
        font-size:clamp(1.8rem,4vw,3.6rem);
        line-height:.95;
        font-weight:1000;
        letter-spacing:-.055em;
        margin-bottom:10px;
    }
    .radio-frequency{
        display:inline-flex;
        gap:8px;
        align-items:center;
        padding:9px 13px;
        border-radius:999px;
        background:rgba(0,0,0,.28);
        border:1px solid rgba(255,255,255,.13);
        color:#fff;
        font-weight:900;
        margin:8px 0 14px;
    }
    .memory-actions{
        display:grid;
        grid-template-columns:repeat(3, minmax(0, 1fr));
        gap:10px;
        margin:14px 0;
    }
    .big-action-note{
        color:#d8d8d8;
        font-size:.92rem;
        line-height:1.35;
        margin-top:8px;
    }
    @media (max-width:900px){
        .memory-inner{grid-template-columns:1fr;}
        .memory-photo{min-height:260px;}
        .memory-photo img{min-height:260px;}
        .memory-actions{grid-template-columns:1fr;}
    }

    .external-button{
        display:inline-block;
        border-radius:999px;
        padding:12px 16px;
        background:#38bdf8;
        color:#00111c !important;
        text-decoration:none !important;
        font-weight:950;
        margin-top:8px;
    }

        .hero-wow:before{
        content:"";
        position:absolute;
        width:72%;
        height:190px;
        left:-10%;
        top:18px;
        background:linear-gradient(90deg, transparent, rgba(30,215,96,.34), rgba(247,201,72,.24), transparent);
        filter:blur(18px);
        transform:rotate(-8deg);
        animation:auroraFlow 8s ease-in-out infinite;
    }
    .accordion-stage{
        margin-top:24px;
        display:flex;
        align-items:center;
        gap:16px;
        background:rgba(0,0,0,.22);
        border:1px solid rgba(255,255,255,.13);
        border-radius:26px;
        padding:14px 16px;
        width:min(520px, 100%);
        animation:glowPulse 4.2s ease-in-out infinite;
    }
    .accordion-man{
        position:relative;
        width:104px;
        height:94px;
        flex:0 0 104px;
        animation:floaty 3.2s ease-in-out infinite;
    }
    .head{
        position:absolute; left:38px; top:0; width:34px; height:34px; border-radius:50%;
        background:linear-gradient(135deg,#ffe0aa,#d59b5b);
        border:2px solid rgba(0,0,0,.25);
    }
    .hat{
        position:absolute; left:27px; top:-5px; width:58px; height:15px; border-radius:50% 50% 12px 12px;
        background:#111; transform:rotate(-5deg);
        box-shadow:0 -8px 0 #222 inset;
    }
    .body{
        position:absolute; left:32px; top:34px; width:44px; height:52px; border-radius:18px 18px 12px 12px;
        background:linear-gradient(135deg,#1f2937,#0f172a);
        border:2px solid rgba(255,255,255,.12);
    }
    .accordion{
        position:absolute; left:11px; top:43px; width:86px; height:36px; display:flex; align-items:center; justify-content:center;
    }
    .box-left,.box-right{
        width:25px; height:36px; border-radius:8px;
        background:linear-gradient(135deg,#f8fafc,#94a3b8);
        border:2px solid #0f172a;
        z-index:2;
    }
    .bellows{
        width:36px; height:31px;
        background:repeating-linear-gradient(90deg,#111827 0 4px,#facc15 4px 8px);
        border-top:2px solid #0f172a;
        border-bottom:2px solid #0f172a;
        animation:squeezeBox .72s ease-in-out infinite;
        transform-origin:center;
    }
    .music-note{
        position:absolute;
        font-size:22px;
        color:#facc15;
        text-shadow:0 0 14px rgba(250,204,21,.7);
        animation:noteFly 2.1s ease-in-out infinite;
    }
    .note1{left:88px; top:24px; animation-delay:0s;}
    .note2{left:72px; top:50px; animation-delay:.55s; color:#1ed760;}
    .note3{left:96px; top:64px; animation-delay:1.05s; color:#fff;}
    .wow-copy{
        min-width:0;
    }
    .wow-copy b{
        display:block;
        color:#fff;
        font-size:1.05rem;
        margin-bottom:4px;
    }
    .wow-copy span{
        color:#d7d7d7;
        font-size:.92rem;
        line-height:1.35;
    }

    .hero{
        position:relative; overflow:hidden; padding:34px; border-radius:34px;
        background:
            radial-gradient(circle at 84% 18%, rgba(247,201,72,.32), transparent 15rem),
            radial-gradient(circle at 16% 26%, rgba(30,215,96,.30), transparent 19rem),
            linear-gradient(135deg, rgba(25,88,42,.96), rgba(16,50,26,.96));
        border:1px solid rgba(255,255,255,.14);
        box-shadow:0 30px 80px rgba(0,0,0,.40);
        margin-bottom:24px;
    }
    .hero-grid{
        display:grid;
        grid-template-columns: minmax(0, 1.25fr) minmax(260px, .75fr);
        gap:28px;
        align-items:center;
    }
    .hero-img-wrap{
        position:relative;
        border-radius:34px;
        overflow:hidden;
        min-height:330px;
        box-shadow:0 24px 70px rgba(0,0,0,.45);
        border:1px solid rgba(255,255,255,.18);
        background:rgba(0,0,0,.24);
    }
    .hero-img-wrap img{
        width:100%;
        height:100%;
        min-height:330px;
        object-fit:cover;
        display:block;
        transform:scale(1.02);
    }
    .hero-img-wrap:after{
        content:"Auðbert Vigfússon";
        position:absolute;
        left:18px;
        bottom:18px;
        background:rgba(0,0,0,.58);
        border:1px solid rgba(255,255,255,.20);
        border-radius:999px;
        color:#fff;
        padding:9px 14px;
        font-weight:950;
        backdrop-filter:blur(10px);
    }
    .pill{
        display:inline-flex;align-items:center;gap:8px;padding:9px 14px;border-radius:999px;
        background:rgba(255,255,255,.10);border:1px solid rgba(255,255,255,.16);
        color:white;font-weight:800;font-size:.95rem;margin:4px 6px 14px 0;
    }
    .hero h1{
        font-size:clamp(2.6rem,7vw,5.8rem);line-height:.92;margin:8px 0 8px;letter-spacing:-.07em;
    }
    .person{
        display:inline-block;color:#111;background:linear-gradient(135deg, #f7c948, #fff1a8);
        padding:8px 16px;border-radius:999px;font-weight:950;font-size:clamp(1.05rem,2vw,1.3rem);
        box-shadow:0 12px 34px rgba(0,0,0,.25);margin:4px 0 14px;
    }
    .hero p{font-size:clamp(1.05rem,2vw,1.35rem);color:#fff;margin:0;}
    .mini-stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px;}
    .stat{background:rgba(0,0,0,.22);border:1px solid rgba(255,255,255,.12);border-radius:18px;padding:12px 14px;}
    .stat b{font-size:1.25rem;}
    .section-card{
        background:rgba(255,255,255,.055); border:1px solid var(--border); border-radius:28px;
        padding:20px; box-shadow:0 18px 50px rgba(0,0,0,.22); margin:14px 0 22px;
    }
    .song-card{
        background:rgba(24,24,24,.88);border:1px solid var(--border);border-radius:25px;
        padding:17px;min-height:286px;transition:all .15s ease;box-shadow:0 16px 44px rgba(0,0,0,.24);
    }
    .song-card:hover{transform:translateY(-3px);border-color:rgba(30,215,96,.54);background:rgba(33,33,33,.95);}
    .cover{
        height:148px;border-radius:21px;
        background:radial-gradient(circle at 25% 20%, rgba(255,255,255,.28), transparent 36%),
                   linear-gradient(135deg, #1ed760, #0c6b33 43%, #f7c948);
        display:flex;align-items:center;justify-content:center;font-size:3.2rem;margin-bottom:14px;
        overflow:hidden;
    }
    .cover img{width:100%;height:100%;object-fit:cover;display:block;}
    .inline-player-box{
        margin:10px 0 18px;
        padding:14px;
        border-radius:22px;
        border:1px solid rgba(30,215,96,.36);
        background:linear-gradient(135deg, rgba(30,215,96,.13), rgba(255,255,255,.045));
        box-shadow:0 16px 38px rgba(0,0,0,.30);
    }
    .inline-player-title{
        font-weight:950;
        color:#fff;
        margin-bottom:8px;
        font-size:.98rem;
    }
    .play-hint{
        color:#d7d7d7;
        font-size:.86rem;
        margin-top:6px;
    }
    .song-title{font-size:1.05rem;font-weight:900;letter-spacing:-.02em;color:white;margin-bottom:4px;}
    .song-artist{color:#bdbdbd;font-size:.94rem;margin-bottom:10px;}
    .tag{font-size:.78rem;color:#111;background:#1ed760;font-weight:950;padding:5px 9px;border-radius:999px;display:inline-block;}
    .filename{color:#858585;font-size:.72rem;margin-top:8px;overflow-wrap:anywhere;}
    .playlist-card{
        border-radius:26px;background:linear-gradient(155deg, rgba(255,255,255,.10), rgba(255,255,255,.035));
        border:1px solid var(--border); padding:18px; height:100%;
    }
    .playlist-card h3{margin-top:0;}
    .playlist-showcase{
        position:relative;
        margin:10px 0 24px;
        padding:22px;
        border-radius:30px;
        border:1px solid rgba(255,255,255,.12);
        background:
            radial-gradient(circle at 14% 18%, rgba(30,215,96,.20), transparent 26rem),
            radial-gradient(circle at 86% 10%, rgba(247,201,72,.18), transparent 22rem),
            rgba(255,255,255,.045);
        box-shadow:0 24px 70px rgba(0,0,0,.34);
        overflow:hidden;
    }
    .playlist-showcase:before{
        content:"";
        position:absolute;
        inset:-80px;
        background:conic-gradient(from 120deg, transparent, rgba(30,215,96,.16), transparent, rgba(247,201,72,.14), transparent);
        animation:slowSpin 12s linear infinite;
        opacity:.65;
        pointer-events:none;
    }
    @keyframes slowSpin{
        from{transform:rotate(0deg);}
        to{transform:rotate(360deg);}
    }
    .playlist-showcase-inner{
        position:relative;
        z-index:1;
    }
    .playlist-kicker{
        display:inline-flex;
        align-items:center;
        gap:8px;
        padding:8px 12px;
        border-radius:999px;
        background:rgba(30,215,96,.14);
        border:1px solid rgba(30,215,96,.34);
        color:#fff;
        font-weight:900;
        margin-bottom:12px;
    }
    .playlist-grid-card{
        position:relative;
        overflow:hidden;
        border-radius:30px !important;
        background:
            radial-gradient(circle at 15% 10%, rgba(247,201,72,.17), transparent 16rem),
            linear-gradient(155deg, rgba(30,215,96,.18), rgba(255,255,255,.045)) !important;
        border:1px solid rgba(255,255,255,.14) !important;
        padding:22px !important;
        min-height:210px !important;
        box-shadow:0 22px 60px rgba(0,0,0,.34) !important;
    }
    .playlist-grid-card:after{
        content:"";
        position:absolute;
        width:160px;
        height:160px;
        right:-54px;
        bottom:-64px;
        border-radius:999px;
        background:radial-gradient(circle, rgba(30,215,96,.22), transparent 66%);
    }
    .playlist-grid-card:hover{
        transform:translateY(-5px) scale(1.012) !important;
        border-color:rgba(247,201,72,.55) !important;
        box-shadow:0 28px 85px rgba(0,0,0,.42), 0 0 34px rgba(30,215,96,.18) !important;
    }
    .playlist-grid-title{
        font-size:1.45rem !important;
        letter-spacing:-.035em;
        text-shadow:0 2px 16px rgba(0,0,0,.35);
    }
    .playlist-grid-desc{
        font-size:1rem !important;
        color:#ececec !important;
    }
    .playlist-badge{
        display:inline-flex;
        margin:0 0 12px;
        padding:7px 11px;
        border-radius:999px;
        background:linear-gradient(135deg, rgba(247,201,72,.95), rgba(255,244,180,.95));
        color:#111;
        font-weight:950;
        font-size:.82rem;
        box-shadow:0 12px 30px rgba(0,0,0,.24);
    }
    .playlist-count{
        background:rgba(0,0,0,.35) !important;
        border:1px solid rgba(255,255,255,.10);
    }
        background:linear-gradient(155deg, rgba(30,215,96,.16), rgba(255,255,255,.045));
        border:1px solid rgba(255,255,255,.12);
        padding:18px;
        min-height:170px;
        box-shadow:0 16px 45px rgba(0,0,0,.25);
        transition:all .15s ease;
        margin-bottom:12px;
    }
    .playlist-grid-card:hover{
        transform:translateY(-3px);
        border-color:rgba(30,215,96,.55);
        background:linear-gradient(155deg, rgba(30,215,96,.24), rgba(255,255,255,.07));
    }
    .playlist-selected-note{
        display:inline-block;
        margin:0 0 14px;
        padding:8px 12px;
        border-radius:999px;
        background:rgba(30,215,96,.16);
        border:1px solid rgba(30,215,96,.35);
        color:#fff;
        font-weight:850;
    }
    .playlist-grid-title{
        font-size:1.15rem;
        font-weight:950;
        color:white;
        margin-bottom:8px;
    }
    .playlist-grid-desc{
        color:#cfcfcf;
        font-size:.9rem;
        line-height:1.35;
        min-height:48px;
    }
    .playlist-count{
        display:inline-flex;
        align-items:center;
        gap:6px;
        margin-top:10px;
        border-radius:999px;
        padding:6px 10px;
        background:rgba(0,0,0,.28);
        color:#fff;
        font-size:.82rem;
        font-weight:850;
    }
    .playlist-song{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.07);}
    .playlist-song small{color:#aaa;}
    .missing{color:#999;font-size:.92rem;margin:6px 0;}
    .youtube-link{
        display:inline-block;
        margin:8px 0 12px;
        padding:10px 14px;
        border-radius:999px;
        background:#ff0033;
        color:#fff !important;
        text-decoration:none !important;
        font-weight:900;
    }
    .youtube-frame-wrap{
        margin:14px 0 18px;
        border-radius:24px;
        overflow:hidden;
        border:1px solid rgba(255,255,255,.14);
        box-shadow:0 18px 45px rgba(0,0,0,.32);
        background:#000;
    }
    .youtube-frame-wrap iframe{
        width:100%;
        aspect-ratio:16/9;
        min-height:360px;
        border:0;
        display:block;
    }
    .playlist-note{
        border-radius:18px;
        border:1px solid rgba(255,255,255,.12);
        background:rgba(255,255,255,.06);
        padding:14px;
        color:#e5e5e5;
        margin:10px 0 16px;
    }
    .gallery-card{
        border-radius:24px;background:rgba(255,255,255,.055);border:1px solid var(--border);padding:12px;height:100%;
        margin-bottom:14px;
    }
    .gallery-card img{
        width:100%;height:310px;object-fit:cover;border-radius:18px;display:block;
        background:rgba(255,255,255,.06);
    }
    .gallery-caption{color:#d7d7d7;font-size:.88rem;margin-top:8px;}
    div.stButton > button{
        border-radius:999px;border:1px solid rgba(255,255,255,.16);
        background:rgba(255,255,255,.08);color:white;font-weight:850;min-height:44px;
    }
    div.stButton > button:hover{border-color:rgba(30,215,96,.65);background:rgba(30,215,96,.22);color:white;}
    audio{width:100%;border-radius:12px;}
    .memory-box{color:#eee;background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:20px;padding:14px;margin-top:10px;}
    .now-playing{
        position:fixed;z-index:999;left:0;right:0;bottom:0;background:rgba(8,8,8,.96);
        backdrop-filter:blur(16px);border-top:1px solid rgba(255,255,255,.12);padding:12px 22px 16px;
        box-shadow:0 -14px 40px rgba(0,0,0,.45);
    }
    .now-playing-title{font-weight:950;font-size:1.05rem;margin-bottom:2px;}
    .now-playing-sub{color:#b3b3b3;font-size:.9rem;}
    @media (max-width:900px){
        .hero-grid{grid-template-columns:1fr;}
        .hero-img-wrap{min-height:260px;}
        .hero-img-wrap img{min-height:260px;}
    }
    @media (max-width:760px){
        .main .block-container{padding-left:.8rem;padding-right:.8rem;}
        .hero{padding:24px;border-radius:26px;}
        .song-card{min-height:auto;}
        .cover{height:125px;}
        .gallery-card img{height:240px;}
    }
    </style>
    """, unsafe_allow_html=True)

def init_state(df):
    if "current_index" not in st.session_state: st.session_state.current_index = 0
    if "favorites" not in st.session_state: st.session_state.favorites = set()
    if "big_mode" not in st.session_state: st.session_state.big_mode = False
    if "active_playlist" not in st.session_state: st.session_state.active_playlist = "Enginn"

def get_song_index_by_title(df, title):
    hits = df.index[df["title"].str.lower() == title.lower()].tolist()
    return int(hits[0]) if hits else None

def playlist_indices(df, playlist):
    out = []
    for title in playlist.get("available_titles", []):
        idx = get_song_index_by_title(df, title)
        if idx is not None:
            out.append(idx)
    return out

def set_current(idx, autoplay=False):
    st.session_state.current_index = int(idx)
    st.session_state.inline_player_index = int(idx)
    st.session_state.autoplay_current = bool(autoplay)
    lines = [
        "Jæja, nú er kominn tími á alvöru nikkustemningu!",
        "Þetta lag kallar á kaffibolla.",
        "Gamlar perlur eldast eins og gott vín.",
        "Nú er nikkukarlinn kominn á fullt!",
        "Þetta er lag sem má spila hátt.",
        "Setjum smá gleði í stofuna!",
        "Ef tærnar byrja að hreyfast er allt að virka.",
    ]
    try:
        st.session_state.mascot_line = random.choice(lines)
    except Exception:
        pass

def current_song(df):
    idx = min(max(st.session_state.current_index, 0), len(df)-1)
    st.session_state.current_index = idx
    return df.iloc[idx]

def cover_html(path, emoji="🎵"):
    if path and Path(str(path)).exists():
        uri = img_to_data_uri(str(path))
        return f"<img src='{uri}' alt='cover'>"
    return emoji

def render_inline_player(row, idx):
    st.markdown(f"""
    <div class="inline-player-box">
        <div class="inline-player-title">🎧 Spila hér: {safe_text(row['title'])}</div>
    </div>
    """, unsafe_allow_html=True)
    render_reliable_audio(row)
    st.markdown("<div class='play-hint'>Ef vafrinn stoppar sjálfvirka spilun, ýttu hér á play. Þú þarft ekki að fara upp á síðuna.</div>", unsafe_allow_html=True)

def render_mascot_panel():
    st.markdown(f"""
    <div class="mascot-panel">
        <div class="accordion-man">
            <div class="hat"></div>
            <div class="head"></div>
            <div class="body"></div>
            <div class="accordion">
                <div class="box-left"></div>
                <div class="bellows"></div>
                <div class="box-right"></div>
            </div>
            <div class="music-note note1">♪</div>
            <div class="music-note note2">♫</div>
            <div class="music-note note3">♬</div>
        </div>
        <div class="mascot-bubble">{safe_text(st.session_state.get("mascot_line", "Nú er nikkustemning!"))}</div>
    </div>
    """, unsafe_allow_html=True)

def render_spilarinn_page():
    st.markdown("""
    <div class="spilarinn-card">
        <h3>📻 Spilarinn.is</h3>
        <p style="color:#ddd;">Spilarinn.is er tengdur hér sem útvarpsviðbót. Þar er hægt að sækja Spilarann og hafa íslenskar útvarpsstöðvar á einum stað.</p>
        <a class="external-button" href="https://spilarinn.is/" target="_blank">Opna Spilarinn.is</a>
    </div>
    """, unsafe_allow_html=True)
    st.components.v1.iframe("https://spilarinn.is/", height=720, scrolling=True)
    st.caption("Ef síðan birtist ekki inni í rammanum er það vegna varna hjá vefnum. Þá virkar hnappurinn fyrir ofan.")

def render_tv_mode(song):
    cover = song.get("cover", "")
    cover_src = img_to_data_uri(cover) if cover and Path(str(cover)).exists() else ""
    cover_html_tv = f"<img src='{cover_src}' alt='cover'>" if cover_src else ""
    st.markdown(f"""
    <div class="tv-mode-wrap">
        <div class="tv-now">
            <div class="tv-cover">{cover_html_tv}</div>
            <div>
                <div class="tv-title">{safe_text(song['title'])}</div>
                <div class="tv-sub">{safe_text(song['artist'])} · {safe_text(song['category'])}</div>
                <div class="mascot-bubble">{safe_text(st.session_state.get("mascot_line", "Tónheimar eru komnir í sjónvarpsham."))}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    render_reliable_audio(song)

def choose_memory_text(song_title=""):
    lines = [
        "Þessi stund kallar á góða tónlist, smá nostalgíu og bros út í annað.",
        "Gamlar myndir og góð lög kunna að opna dyr að bestu minningunum.",
        "Setjum kaffið á könnuna, leyfum nikkunni að anda og rifjum upp góða tíma.",
        "Þetta er ein af þessum stundum sem maður vill leyfa að lifa aðeins lengur.",
        "Tónlistin fer beint í hjartað þegar myndirnar fylgja með.",
        "Hér er smá ferðalag aftur í tímann — með Auðberti í fararbroddi.",
        "Nú er komið að gullmola úr safninu. Halló gamla góða stemning!",
    ]
    if song_title:
        lines.append(f"Við leyfum laginu „{song_title}“ að leiða okkur inn í næstu minningu.")
    return random.choice(lines)

def get_memory_image(media):
    images = media.get("images", [])
    if not images:
        return "", "Minningamynd"
    idx = st.session_state.get("memory_image_index", 0) % len(images)
    img = images[idx]
    return img.get("file_url", ""), img.get("title", "Minningamynd")

def pick_random_song(df):
    if len(df) == 0:
        return None
    idx = random.choice(list(df.index))
    set_current(idx, autoplay=True)
    return df.loc[idx]

def start_memory_machine(df, media):
    song = pick_random_song(df)
    images = media.get("images", [])
    if images:
        st.session_state.memory_image_index = random.randint(0, len(images)-1)
    title = song["title"] if song is not None else ""
    st.session_state.memory_text = choose_memory_text(title)
    st.session_state.memory_mode = True
    st.session_state.radio_audbert = False
    st.session_state.mascot_line = random.choice([
        "Minningarvélin er ræst — haltu þér í kaffibollann!",
        "Nú fer nikkukarlinn í tímaferðalag.",
        "Ég fann gullmola úr safninu!",
        "Þetta gæti orðið falleg stund.",
    ])

def start_radio_audbert(df, playlists):
    if len(df) > 0:
        pick_random_song(df)
    st.session_state.radio_audbert = True
    st.session_state.memory_mode = False
    st.session_state.party_mode = True
    st.session_state.mascot_line = random.choice([
        "Góðan daginn, þú ert á Radio Auðbert!",
        "Næsta lag kemur beint úr gullkistunni.",
        "Radio Auðbert sendir út með bros á vör.",
        "Við spilum það sem skiptir máli: perlur og minningar.",
    ])

def render_memory_machine(df, media):
    song = current_song(df)
    img_url, img_title = get_memory_image(media)
    img_src = img_to_data_uri(img_url) if img_url and Path(str(img_url)).exists() else ""
    img_html = f"<img src='{img_src}' alt='{safe_text(img_title)}'>" if img_src else ""
    st.markdown(f"""
    <div class="memory-machine">
        <div class="memory-inner">
            <div class="memory-photo">{img_html}</div>
            <div>
                <div class="memory-kicker">🎞️ Minningarvélin</div>
                <div class="memory-title">Mynd, lag og minning</div>
                <div class="memory-text">{safe_text(st.session_state.get("memory_text", ""))}</div>
                <div class="radio-frequency">🎵 Nú valið: {safe_text(song['title'])}</div>
                <div class="mascot-bubble">{safe_text(st.session_state.get("mascot_line", ""))}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    render_reliable_audio(song)

def render_radio_audbert(df, playlists):
    song = current_song(df)
    st.markdown(f"""
    <div class="radio-panel">
        <div class="radio-title">📻 Radio Auðbert</div>
        <div class="radio-frequency">FM 100.7 · Gamlar perlur · Nikkustemning</div>
        <p style="color:#e7e7e7; font-size:1.05rem; margin:0 0 12px;">
            Sjálfvirk blanda af lögum, myndum og stemningu. Ýttu á næsta random þegar þú vilt nýja sendingu.
        </p>
        <div class="mascot-bubble">{safe_text(st.session_state.get("mascot_line", ""))}</div>
    </div>
    """, unsafe_allow_html=True)
    render_reliable_audio(song)

def render_memory_page(df, media, playlists):
    st.markdown("## 🎞️ Minningarvélin + 📻 Radio Auðbert")
    st.caption("Veldu upplifun: minningavél með mynd + lag eða Radio Auðbert sem velur stemningu fyrir þig.")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎞️ Ræsa minningarvél", use_container_width=True):
            start_memory_machine(df, media)
            safe_rerun()
    with c2:
        if st.button("📻 Radio Auðbert", use_container_width=True):
            start_radio_audbert(df, playlists)
            safe_rerun()
    with c3:
        if st.button("🎲 Ný tilviljun", use_container_width=True):
            if st.session_state.get("radio_audbert", False):
                start_radio_audbert(df, playlists)
            else:
                start_memory_machine(df, media)
            safe_rerun()

    st.markdown("""
    <div class="big-action-note">
        Minningarvélin velur mynd, lag og texta. Radio Auðbert setur partýham í gang og velur næsta gullmola.
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.get("radio_audbert", False):
        render_radio_audbert(df, playlists)
    elif st.session_state.get("memory_mode", False):
        render_memory_machine(df, media)
    else:
        st.info("Smelltu á Ræsa minningarvél eða Radio Auðbert til að byrja.")

def render_card(row, idx):
    st.markdown(f"""
    <div class="song-card">
        <div class="cover">{cover_html(row.get('cover',''))}</div>
        <div class="song-title">{safe_text(row['title'])}</div>
        <div class="song-artist">{safe_text(row['artist'])}</div>
        <span class="tag">{safe_text(row['category'])}</span>
        <div class="filename">{safe_text(row.get('original_filename',''))}</div>
    </div>
    """, unsafe_allow_html=True)
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("▶ Spila", key=f"play_{idx}", use_container_width=True):
            set_current(idx); safe_rerun()
    with c2:
        fav = idx in st.session_state.favorites
        if st.button("💚" if fav else "🤍", key=f"fav_{idx}", use_container_width=True):
            if fav: st.session_state.favorites.remove(idx)
            else: st.session_state.favorites.add(idx)
            safe_rerun()

    if st.session_state.get("inline_player_index") == idx:
        render_inline_player(row, idx)

def render_gallery(media):
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🖼️ Myndir og myndband")
    st.caption("Myndirnar sem þú sendir eru nú vistaðar inni í verkefninu og birtast án Google Drive vandamála.")

    videos = media.get("videos", [])
    if videos:
        st.markdown("### 🎬 Myndband")
        for vid in videos:
            thumb = vid.get("thumbnail", "")
            thumb_src = img_to_data_uri(thumb) if thumb and Path(thumb).exists() else ""
            video_url = vid.get("file_url", "")
            if video_url and Path(video_url).exists():
                st.video(video_url)
            elif thumb_src:
                st.markdown(f'''
                <div class="gallery-card">
                    <img src="{thumb_src}" alt="{safe_text(vid.get('title','myndband'))}">
                    <div class="gallery-caption"><b>{safe_text(vid.get('title','Myndband'))}</b><br>{safe_text(vid.get('caption',''))}</div>
                </div>
                ''', unsafe_allow_html=True)

    st.markdown("### 📷 Myndasafn")
    images = media.get("images", [])
    cols = st.columns(3)
    for i, img in enumerate(images):
        with cols[i % 3]:
            url = img.get("file_url","")
            if url.startswith("assets/") and Path(url).exists():
                url = img_to_data_uri(url)
            st.markdown(f'''
            <div class="gallery-card">
                <img src="{url}" alt="{safe_text(img.get('title','mynd'))}">
                <div class="gallery-caption"><b>{safe_text(img.get('title',''))}</b><br>{safe_text(img.get('caption',''))}</div>
            </div>
            ''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

def render_playlists(df, playlists):
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📺 YouTube playlistar")
    st.caption("Hér eru bara YouTube playlistarnir sem þú vilt hafa inni. Veldu flís og spilaðu listann beint í vefnum.")

    names = list(playlists.keys())
    current = st.session_state.active_playlist if st.session_state.active_playlist in names else names[0]
    selected = current

    st.markdown("""
    <div class="playlist-showcase">
      <div class="playlist-showcase-inner">
        <div class="playlist-kicker">✨ Sérvaldar íslenskar tónlistarperlur</div>
    """, unsafe_allow_html=True)
    st.markdown("### Veldu lista")
    cols = st.columns(2)
    for i, name in enumerate(names):
        playlist = playlists[name]
        indices = playlist_indices(df, playlist)
        has_youtube = bool(playlist.get("youtube_playlist", {}))
        count_label = f"{len(indices)} lög" if indices else ("YouTube playlisti" if has_youtube else "0 lög")
        with cols[i % 3]:
            st.markdown(f"""
            <div class="playlist-grid-card">
                <div class="playlist-badge">{safe_text(playlist.get("badge", "Playlisti"))}</div>
                <div class="playlist-grid-title">{safe_text(name)}</div>
                <div class="playlist-grid-desc">{safe_text(playlist.get("description",""))}</div>
                <div class="playlist-count">🎵 {safe_text(count_label)}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Velja", key=f"choose_playlist_{i}", use_container_width=True):
                st.session_state.active_playlist = name
                st.session_state.youtube_autoplay = bool(playlist.get("youtube_playlist", {}))
                safe_rerun()

    st.markdown("</div></div>", unsafe_allow_html=True)

    selected = st.session_state.active_playlist if st.session_state.active_playlist in names else names[0]
    playlist = playlists[selected]
    indices = playlist_indices(df, playlist)
    has_youtube = bool(playlist.get("youtube_playlist", {}))

    st.divider()
    st.markdown(f"<span class='playlist-selected-note'>Valinn playlisti · smelltu á Velja til að ræsa</span>", unsafe_allow_html=True)
    st.markdown(f"## {safe_text(selected)}")

    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        if st.button("▶ Spila playlist", use_container_width=True):
            if indices:
                st.session_state.current_index = indices[0]
                safe_rerun()
            elif has_youtube:
                st.session_state.youtube_autoplay = True
                st.info("YouTube-spilarinn opnast fyrir neðan og reynir að fara strax af stað.")
                safe_rerun()
            else:
                st.warning("Engar spilanlegar skrár fundust í þessum lista.")
    with c2:
        if st.button("🎲 Random úr lista", use_container_width=True):
            if indices:
                st.session_state.current_index = random.choice(indices)
                safe_rerun()
            elif has_youtube:
                st.info("YouTube-listinn ræður röðinni í spilaranum.")
            else:
                st.warning("Engar spilanlegar skrár fundust í þessum lista.")
    with c3:
        st.info(playlist.get("description",""))

    st.markdown("<div class='playlist-card'>", unsafe_allow_html=True)

    yt_playlist = playlist.get("youtube_playlist", {})
    if yt_playlist:
        raw_embed_url = yt_playlist.get("embed_url", "")
        if st.session_state.get("youtube_autoplay", False):
            sep = "&" if "?" in raw_embed_url else "?"
            raw_embed_url = f"{raw_embed_url}{sep}autoplay=1&rel=0"
        embed_url = safe_text(raw_embed_url)
        original_url = safe_text(yt_playlist.get("url", ""))
        title = safe_text(yt_playlist.get("title", "YouTube playlist"))
        st.markdown(f"""
        <div class="playlist-note">
            <b>{title}</b><br>
            Þessi playlisti hefur tónlist á bak við sig. Þegar þú smellir á Velja reynir YouTube-spilarinn að fara strax af stað.
        </div>
        <div class="youtube-frame-wrap">
            <iframe src="{embed_url}" title="{title}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
        </div>
        <a class="youtube-link" href="{original_url}" target="_blank">▶ Opna playlistann á YouTube</a>
        <div class="play-hint">Ef vafrinn stoppar sjálfvirka spilun þarf bara að ýta einu sinni á play í YouTube-spilaranum.</div>
        """, unsafe_allow_html=True)

    if playlist.get("available_titles", []):
        st.markdown("#### Í Tónheima-spilaranum")
    for nr, title in enumerate(playlist.get("available_titles", []), start=1):
        idx = get_song_index_by_title(df, title)
        if idx is not None:
            row = df.loc[idx]
            cc1, cc2 = st.columns([4,1])
            with cc1:
                st.markdown(f"<div class='playlist-song'><div><b>{nr}. {safe_text(row['title'])}</b><br><small>{safe_text(row['artist'])} · {safe_text(row['category'])}</small></div></div>", unsafe_allow_html=True)
            with cc2:
                if st.button("▶", key=f"pl_{selected}_{idx}", use_container_width=True):
                    st.session_state.current_index = idx
                    safe_rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

inject_css()
df = load_songs()
playlists = load_playlists()
media = load_media()
init_state(df)

playlist_names = ["Enginn"] + list(playlists.keys())

with st.sidebar:
    st.title("🎵 Tónheimar")
    st.caption(PERSON_NAME)
    st.toggle("Stórir takkar", key="big_mode")
    st.divider()
    page = st.radio("Sýna", ["Lög", "Playlistar", "Myndir", "Minningarvélin", "Spilarinn.is"], index=0)
    st.divider()
    st.session_state.party_mode = st.toggle("🎉 Partýhamur", value=st.session_state.get("party_mode", False))
    st.session_state.tv_mode = st.toggle("📺 Sjónvarpshamur", value=st.session_state.get("tv_mode", False))
    category = "Öll lög"
    st.caption("YouTube playlistar eru valdir með flísum á Playlistar-síðunni.")
    if st.button("Hreinsa playlist-val", use_container_width=True):
        st.session_state.active_playlist = "Enginn"
        safe_rerun()
    search = st.text_input("Leita", placeholder="Lag, listamaður eða flokkur")
    show_favorites = st.checkbox("Sýna bara uppáhald")
    st.divider()
    st.write(f"**Lög:** {len(df)}")
    st.write(f"**Playlistar:** {len(playlists)}")
    st.write(f"**Uppáhald:** {len(st.session_state.favorites)}")
    if st.button("🔄 Endurhlaða vef", use_container_width=True):
        safe_rerun()
    if st.button("🧹 Hreinsa hljóð-cache", use_container_width=True):
        import shutil as _shutil
        _shutil.rmtree("audio_cache", ignore_errors=True)
        st.success("Hljóð-cache hreinsað. Veldu lag aftur.")

hero_img = media.get("hero_image", "")
hero_uri = img_to_data_uri(hero_img) if hero_img else ""
hero_img_html = f"<div class='hero-img-wrap'><img src='{hero_uri}' alt='Auðbert Vigfússon'></div>" if hero_uri else ""

st.markdown(f"""
<div class="hero">
    <div class="hero-wow"></div>
    <div class="hero-grid">
        <div>
            <h1>{APP_NAME}</h1>
            <div class="person">{PERSON_NAME}</div>
            <p>{SUBTITLE}</p>
            <div class="mini-stats">
                <div class="stat"><b>{len(df)}</b><br>lög í safni</div>
                <div class="stat"><b>{len(playlists)}</b><br>playlistar</div>
                <div class="stat"><b>{len(media.get("images", []))}</b><br>myndir</div>
            </div>
            <div class="accordion-stage">
                <div class="accordion-man">
                    <div class="hat"></div>
                    <div class="head"></div>
                    <div class="body"></div>
                    <div class="accordion">
                        <div class="box-left"></div>
                        <div class="bellows"></div>
                        <div class="box-right"></div>
                    </div>
                    <div class="music-note note1">♪</div>
                    <div class="music-note note2">♫</div>
                    <div class="music-note note3">♬</div>
                </div>
                <div class="wow-copy">
                    <b>Nikku-stemning í loftinu!</b>
                    <span>Veldu lag, hallaðu þér aftur og leyfðu Auðberts-safninu að lifna við.</span>
                </div>
            </div>
        </div>
        {hero_img_html}
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="section-card">
    <h3>✨ Velkomin í Tónheima</h3>
    <p style="color:#ddd; font-size:1.02rem; margin-bottom:0;">
        Hér sameinast lögin, myndirnar og minningarnar í litlu fjölskyldu-tónlistarsafni.
        Ræstu Minningarvélina, kveiktu á Radio Auðbert eða leyfðu harmonikku-lukkudýrinu að velja næstu stemningu.
    </p>
</div>
""", unsafe_allow_html=True)

if st.session_state.party_mode:
    st.markdown("""
    <div class="party-banner">
        <h2>🎉 Partýhamur virkur!</h2>
        <p>Nú er veisla: glow, nótur, nikkukarl og íslenskar tónlistarperlur.</p>
    </div>
    """, unsafe_allow_html=True)

render_mascot_panel()

st.markdown("### 🚀 Snögg ræsing")
q1, q2, q3 = st.columns(3)
with q1:
    if st.button("🎞️ Ræsa minningarvél", use_container_width=True):
        start_memory_machine(df, media)
        page = "Minningarvélin"
        safe_rerun()
with q2:
    if st.button("📻 Radio Auðbert", use_container_width=True):
        start_radio_audbert(df, playlists)
        page = "Minningarvélin"
        safe_rerun()
with q3:
    if st.button("🎉 Veislu-random", use_container_width=True):
        st.session_state.party_mode = True
        start_memory_machine(df, media)
        page = "Minningarvélin"
        safe_rerun()

if st.session_state.tv_mode:
    render_tv_mode(current_song(df))

if st.session_state.big_mode:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🧓 Einfalt viðmót")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🎲 Spila eitthvað gott", use_container_width=True):
            st.session_state.current_index = random.randint(0, len(df)-1); safe_rerun()
    with c2:
        if st.button("⭐ Aðallagið", use_container_width=True):
            st.session_state.current_index = 0; safe_rerun()
    with c3:
        active = st.session_state.active_playlist
        if st.button("▶ Spila valinn playlist", use_container_width=True):
            if active in playlists:
                idxs = playlist_indices(df, playlists[active])
                if idxs:
                    st.session_state.current_index = idxs[0]; safe_rerun()
    st.markdown('</div>', unsafe_allow_html=True)

song = current_song(df)
st.subheader("Nú í spilun")
left, right = st.columns([1.1, 2.7])
with left:
    st.markdown(f"""
    <div class="song-card">
        <div class="cover">{cover_html(song.get('cover',''), '🎶')}</div>
        <div class="song-title">{safe_text(song['title'])}</div>
        <div class="song-artist">{safe_text(song['artist'])}</div>
        <span class="tag">{safe_text(song['category'])}</span>
        <div class="filename">{safe_text(song.get('original_filename',''))}</div>
    </div>
    """, unsafe_allow_html=True)
with right:
    render_reliable_audio(song)
    active_playlist = st.session_state.active_playlist
    nav_indices = playlist_indices(df, playlists[active_playlist]) if active_playlist in playlists else list(df.index)
    if not nav_indices:
        nav_indices = list(df.index)
    try:
        pos = nav_indices.index(st.session_state.current_index)
    except ValueError:
        pos = 0
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        if st.button("⏮ Fyrra", use_container_width=True):
            st.session_state.current_index = nav_indices[max(0, pos-1)]
            safe_rerun()
    with c2:
        if st.button("⏭ Næsta", use_container_width=True):
            st.session_state.current_index = nav_indices[min(len(nav_indices)-1, pos+1)]
            safe_rerun()
    with c3:
        if st.button("🎲 Random", use_container_width=True):
            st.session_state.current_index = random.choice(nav_indices)
            safe_rerun()
    with c4:
        fav = st.session_state.current_index in st.session_state.favorites
        if st.button("💚 Uppáhald" if not fav else "✅ Uppáhald", use_container_width=True):
            if fav: st.session_state.favorites.remove(st.session_state.current_index)
            else: st.session_state.favorites.add(st.session_state.current_index)
            safe_rerun()
    if active_playlist in playlists:
        if playlist_indices(df, playlists[active_playlist]):
            st.success(f"Playlist mode: {active_playlist} · lag {pos+1} af {len(nav_indices)}")
        else:
            st.warning(f"Playlist mode: {active_playlist} · YouTube/hugmyndalisti án hljóðskrár ennþá")
    if song.get("memory"):
        st.markdown(f"<div class='memory-box'><b>Minning:</b><br>{safe_text(song['memory'])}</div>", unsafe_allow_html=True)

if page == "Spilarinn.is":
    render_spilarinn_page()
elif page == "Minningarvélin":
    render_memory_page(df, media, playlists)
elif page == "Myndir":
    render_gallery(media)
elif page == "Playlistar":
    render_playlists(df, playlists)
else:
    st.divider()
    st.subheader("Lagalisti")

    categories_inline = ["Öll lög"] + sorted([c for c in df["category"].unique() if c])
    if "inline_category" not in st.session_state:
        st.session_state.inline_category = "Öll lög"

    st.markdown("#### Flokkar")
    cat_cols = st.columns(min(4, len(categories_inline)))
    for i, cat_name in enumerate(categories_inline):
        with cat_cols[i % len(cat_cols)]:
            if st.button(cat_name, key=f"cat_btn_{i}", use_container_width=True):
                st.session_state.inline_category = cat_name
                safe_rerun()

    category = st.session_state.inline_category
    filtered = df.copy()
    if st.session_state.active_playlist in playlists:
        idxs = playlist_indices(df, playlists[st.session_state.active_playlist])
        filtered = filtered[filtered.index.isin(idxs)]
        st.info(f"Sýni playlist: {st.session_state.active_playlist}")
    if category != "Öll lög":
        filtered = filtered[filtered["category"] == category]
    if search.strip():
        s = search.strip().lower()
        filtered = filtered[
            filtered["title"].str.lower().str.contains(s, na=False) |
            filtered["artist"].str.lower().str.contains(s, na=False) |
            filtered["category"].str.lower().str.contains(s, na=False) |
            filtered["original_filename"].str.lower().str.contains(s, na=False)
        ]
    if show_favorites:
        filtered = filtered[filtered.index.isin(st.session_state.favorites)]
    if len(filtered) == 0:
        st.warning("Engin lög fundust í Tónheima-spilaranum fyrir þessa síu. YouTube-listar spilast undir Playlistar.")
    else:
        cols = st.columns(4)
        for n, (idx, row) in enumerate(filtered.iterrows()):
            with cols[n % 4]:
                render_card(row, idx)

st.markdown(f"""
<div class="now-playing">
    <div class="now-playing-title">🎧 {APP_NAME} · {PERSON_NAME}</div>
    <div class="now-playing-sub">Auðbert er í header. Playlistar og lagalisti sýna bara efni sem hefur tónlist á bak við sig. YouTube playlisti er nú embeddaður sem alvöru listi með upphafslagi. Innbyggði audio-spilarinn þarf mp3/wav skrár.</div>
</div>
""", unsafe_allow_html=True)
