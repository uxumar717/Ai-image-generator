"""
AI Horde Image Generator
=========================
A Streamlit front-end for the AI Horde (aihorde.net) crowdsourced
Stable Diffusion cluster. Free to use — no billing, ever.

Flow:
  1. POST /v2/generate/async   -> submit prompt, get request id
  2. GET  /v2/generate/check/{id}  -> cheap poll (queue position, wait time)
  3. GET  /v2/generate/status/{id} -> full poll (returns image once done)
  4. DELETE /v2/generate/status/{id} -> cancel a running job

Run:
    pip install -r requirements.txt
    streamlit run app.py
"""

import base64
import time
from io import BytesIO

import requests
import streamlit as st
from PIL import Image

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

BASE_URL = "https://aihorde.net/api/v2"
CLIENT_AGENT = "streamlit-horde-generator:1.0:github.com/anonymous"
ANON_KEY = "0000000000"

DEFAULT_HEADERS_EXTRA = {"Client-Agent": CLIENT_AGENT}

SAMPLERS = [
    "k_lms", "k_heun", "k_euler", "k_euler_a", "k_dpm_2", "k_dpm_2_a",
    "k_dpm_fast", "k_dpm_adaptive", "k_dpmpp_2s_a", "k_dpmpp_2m",
    "k_dpmpp_sde", "DDIM",
]

st.set_page_config(page_title="✨ Cutie AI Art Generator", page_icon="🎀", layout="wide")

# --------------------------------------------------------------------------
# Cute pastel theme 💕
# --------------------------------------------------------------------------

st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(160deg, #ffe6f2 0%, #ffe9fb 35%, #eee3ff 70%, #e3f0ff 100%);
    }
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #ffd6ec 0%, #f3d6ff 100%);
        border-right: 3px dashed #ff9ecf;
    }
    h1, h2, h3 {
        color: #d6389a !important;
        font-family: 'Comic Sans MS', 'Trebuchet MS', sans-serif;
    }
    .stButton>button {
        background: linear-gradient(90deg, #ff9ecf, #c9a0ff);
        color: white;
        border-radius: 20px;
        border: none;
        font-weight: bold;
        padding: 0.5em 1.2em;
        box-shadow: 0 3px 8px rgba(255, 150, 220, 0.5);
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #ff7fc4, #b183ff);
        color: white;
        transform: scale(1.03);
    }
    .stTextInput>div>div>input, .stTextArea textarea {
        background-color: #fff0fa;
        border-radius: 12px;
        border: 2px solid #ffb3e0;
    }
    div[data-baseweb="select"] {
        border-radius: 12px;
    }
    .stDownloadButton>button {
        background: linear-gradient(90deg, #a0e7ff, #c9a0ff);
        color: #4a2b5c;
        border-radius: 20px;
        border: none;
        font-weight: bold;
    }
    div[data-testid="stCaptionContainer"] {
        color: #a35bb5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# API helpers
# --------------------------------------------------------------------------

def api_headers(api_key: str) -> dict:
    headers = {"apikey": api_key or ANON_KEY, "Content-Type": "application/json"}
    headers.update(DEFAULT_HEADERS_EXTRA)
    return headers


@st.cache_data(ttl=60, show_spinner=False)
def get_active_models():
    """Fetch currently online image models from the horde."""
    try:
        resp = requests.get(
            f"{BASE_URL}/status/models",
            params={"type": "image"},
            headers=DEFAULT_HEADERS_EXTRA,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # Sort by worker count (more workers = faster turnaround)
        data.sort(key=lambda m: m.get("count", 0), reverse=True)
        return data
    except Exception as e:
        st.session_state["_model_fetch_error"] = str(e)
        return []


def get_heartbeat():
    try:
        resp = requests.get(f"{BASE_URL}/status/heartbeat", headers=DEFAULT_HEADERS_EXTRA, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def find_user(api_key: str):
    try:
        resp = requests.get(f"{BASE_URL}/find_user", headers=api_headers(api_key), timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def submit_generation(api_key: str, payload: dict):
    resp = requests.post(f"{BASE_URL}/generate/async", headers=api_headers(api_key), json=payload, timeout=20)
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"Submit failed ({resp.status_code}): {resp.text}")
    return resp.json()["id"]


def check_generation(request_id: str):
    resp = requests.get(f"{BASE_URL}/generate/check/{request_id}", headers=DEFAULT_HEADERS_EXTRA, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_generation_status(request_id: str, api_key: str):
    resp = requests.get(f"{BASE_URL}/generate/status/{request_id}", headers=api_headers(api_key), timeout=20)
    resp.raise_for_status()
    return resp.json()


def cancel_generation(request_id: str, api_key: str):
    try:
        requests.delete(f"{BASE_URL}/generate/status/{request_id}", headers=api_headers(api_key), timeout=15)
    except Exception:
        pass


def decode_image(gen_entry: dict):
    """A generation entry's 'img' field is either a base64 string or a URL
    (when the 'r2' upload param is used)."""
    img_field = gen_entry.get("img", "")
    if img_field.startswith("http"):
        r = requests.get(img_field, timeout=30)
        r.raise_for_status()
        return Image.open(BytesIO(r.content))
    else:
        return Image.open(BytesIO(base64.b64decode(img_field)))


# --------------------------------------------------------------------------
# Sidebar — API key, model, generation params
# --------------------------------------------------------------------------

with st.sidebar:
    st.title("🎀 Settings")

    api_key = st.text_input(
        "🔑 AI Horde API Key",
        value=st.session_state.get("api_key", ""),
        type="password",
        help="Leave blank to use the anonymous key (0000000000) — works, but "
             "sits at the back of the queue. Get a free key at aihorde.net.",
    )
    st.session_state["api_key"] = api_key
    effective_key = api_key.strip() or ANON_KEY

    if st.button("💖 Check account / kudos"):
        info = find_user(effective_key)
        if info:
            st.success(
                f"👤 User: **{info.get('username', 'anonymous')}**  \n"
                f"✨ Kudos: **{info.get('kudos', 0):.0f}**"
            )
        else:
            st.error("😿 Couldn't reach the horde or invalid key.")

    st.divider()
    st.subheader("🖌️ Model")

    models = get_active_models()
    if models:
        model_labels = [f"🌸 {m['name']}  ({m.get('count', 0)} workers)" for m in models]
        model_names = [m["name"] for m in models]
        default_idx = 0
        chosen_idx = st.selectbox(
            "Active model",
            options=range(len(model_names)),
            format_func=lambda i: model_labels[i],
            index=default_idx,
        )
        selected_model = model_names[chosen_idx]
    else:
        st.warning("⚠️ Could not fetch live model list — using a common default.")
        selected_model = st.text_input("Model name", value="stable_diffusion")

    if st.button("🔄 Refresh model list"):
        get_active_models.clear()
        st.rerun()

    st.divider()
    st.subheader("🧁 Image parameters")

    col_a, col_b = st.columns(2)
    with col_a:
        width = st.selectbox("↔️ Width", [512, 576, 640, 704, 768, 832, 896, 960, 1024], index=0)
    with col_b:
        height = st.selectbox("↕️ Height", [512, 576, 640, 704, 768, 832, 896, 960, 1024], index=0)

    steps = st.slider("👣 Steps", min_value=1, max_value=50, value=25)
    cfg_scale = st.slider("🎯 CFG scale", min_value=1.0, max_value=20.0, value=7.5, step=0.5)
    sampler = st.selectbox("🌀 Sampler", SAMPLERS, index=SAMPLERS.index("k_euler_a"))
    n_images = st.slider("🖼️ Number of images", min_value=1, max_value=4, value=1)
    seed = st.text_input("🌱 Seed (optional, blank = random)", value="")
    nsfw_allowed = st.checkbox("🔞 Allow NSFW content", value=False)

    st.divider()
    st.caption(
        "💌 The AI Horde is a free, volunteer-run GPU cluster. Jobs queue "
        "asynchronously — expect anywhere from a few seconds to a couple "
        "minutes depending on load and your kudos priority. 🌈"
    )


# --------------------------------------------------------------------------
# Main area — prompt input + generate
# --------------------------------------------------------------------------

st.title("🎀✨ Cutie AI Art Generator ✨🎀")
st.write("💕 Free, crowdsourced Stable Diffusion — powered by kind volunteers' GPUs! 🌸")

prompt = st.text_area("💭 Prompt", placeholder="A cinematic photo of a red fox in a snowy forest, golden hour lighting ✨", height=100)
negative_prompt = st.text_area("🚫 Negative prompt (optional)", placeholder="blurry, low quality, watermark", height=68)

col1, col2 = st.columns([1, 1])
generate_clicked = col1.button("🪄 Generate!", type="primary", use_container_width=True)
cancel_clicked = col2.button("💔 Cancel current job", use_container_width=True)

if "request_id" not in st.session_state:
    st.session_state.request_id = None

if cancel_clicked and st.session_state.request_id:
    cancel_generation(st.session_state.request_id, effective_key)
    st.session_state.request_id = None
    st.warning("🥺 Cancelled.")

if generate_clicked:
    if not prompt.strip():
        st.error("💗 Please enter a prompt first!")
    else:
        full_prompt = prompt.strip()
        if negative_prompt.strip():
            full_prompt += f" ### {negative_prompt.strip()}"

        payload = {
            "prompt": full_prompt,
            "params": {
                "sampler_name": sampler,
                "cfg_scale": cfg_scale,
                "height": height,
                "width": width,
                "steps": steps,
                "n": n_images,
            },
            "models": [selected_model],
            "nsfw": nsfw_allowed,
            "censor_nsfw": not nsfw_allowed,
            "r2": True,
            "shared": False,
        }
        if seed.strip():
            payload["params"]["seed"] = seed.strip()

        try:
            with st.spinner("🎡 Submitting job to the horde..."):
                request_id = submit_generation(effective_key, payload)
            st.session_state.request_id = request_id
            st.success(f"🎉 Job submitted! Request ID: `{request_id}`")
        except Exception as e:
            st.error(f"💥 Submission failed: {e}")
            st.session_state.request_id = None

# --------------------------------------------------------------------------
# Poll loop
# --------------------------------------------------------------------------

if st.session_state.request_id:
    request_id = st.session_state.request_id
    status_box = st.empty()
    progress_box = st.empty()
    image_box = st.container()

    done = False
    faulted = False
    poll_count = 0

    while not done and not faulted:
        try:
            check = check_generation(request_id)
        except Exception as e:
            status_box.error(f"😢 Lost connection while polling: {e}")
            break

        done = check.get("done", False)
        faulted = check.get("faulted", False)
        queue_position = check.get("queue_position", "?")
        wait_time = check.get("wait_time", "?")
        processing = check.get("processing", 0)
        waiting = check.get("waiting", 0)

        status_box.info(
            f"🌟 Status — processing: **{processing}** 🎨, waiting: **{waiting}** ⏱️, "
            f"queue position: **{queue_position}** 🎫, est. wait: **{wait_time}s** ⌛"
        )
        progress_box.progress(min(1.0, poll_count / 30))

        if faulted:
            status_box.error("💔 The horde reported this job faulted (couldn't be completed). Try again or change the model.")
            st.session_state.request_id = None
            break

        if done:
            status_box.success("✅💖 Done! Fetching your image(s)...")
            try:
                result = get_generation_status(request_id, effective_key)
                generations = result.get("generations", [])
                progress_box.empty()
                with image_box:
                    cols = st.columns(len(generations)) if generations else []
                    for gen, col in zip(generations, cols):
                        try:
                            img = decode_image(gen)
                            with col:
                                st.image(img, caption=f"🌱 Seed: {gen.get('seed', '?')} · 🧑‍🎨 Worker: {gen.get('worker_name', '?')}", use_container_width=True)
                                buf = BytesIO()
                                img.save(buf, format="PNG")
                                st.download_button(
                                    "💾 Download PNG",
                                    data=buf.getvalue(),
                                    file_name=f"horde_{gen.get('id', request_id)}.png",
                                    mime="image/png",
                                )
                        except Exception as img_err:
                            col.error(f"😿 Could not decode image: {img_err}")
            except Exception as e:
                status_box.error(f"💥 Failed to fetch final image: {e}")
            st.session_state.request_id = None
            break

        poll_count += 1
        time.sleep(3)
