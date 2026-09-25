# AI Horde Image Generator (Streamlit)

A free Stable Diffusion image generator built on the **AI Horde** — a
crowdsourced GPU cluster donated by volunteers. No billing, no API costs.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`).

## Using it

1. **API key (sidebar)** — optional. Leave blank to use the anonymous key
   (`0000000000`), which works fine but gets lowest queue priority. Get a
   free personal key at https://aihorde.net (Register), which also earns
   you kudos over time for faster turnaround.
2. **Model** — the sidebar pulls the list of currently *online* models
   live from the horde (workers rotate models, so availability changes).
   Pick one with more workers for a faster result.
3. **Parameters** — width/height, steps, CFG scale, sampler, number of
   images, optional seed, and an NSFW toggle.
4. **Prompt** — type your prompt (and optional negative prompt) and hit
   **Generate**.
5. The app submits the job, then polls automatically every ~3 seconds,
   showing queue position and estimated wait time, until the image is
   ready — this can take anywhere from a few seconds to a couple of
   minutes depending on horde load. Images appear inline with a download
   button. You can cancel a running job with the **Cancel** button.

## How it works (API flow)

| Step | Endpoint |
|---|---|
| Submit | `POST /v2/generate/async` |
| Cheap poll | `GET /v2/generate/check/{id}` |
| Full poll (returns image) | `GET /v2/generate/status/{id}` |
| Cancel | `DELETE /v2/generate/status/{id}` |
| Live model list | `GET /v2/status/models` |
| Horde health | `GET /v2/status/heartbeat` |
| Account/kudos lookup | `GET /v2/find_user` |

Images are requested via Cloudflare R2 upload (`"r2": true`), so the
`img` field returned per generation is usually a URL; the app also
handles the base64 fallback case.

## Notes / troubleshooting

- **"Job faulted"**: usually means the chosen model went offline mid-job
  or params were incompatible with it — pick a different (more popular)
  model and retry.
- **Slow generations**: the anonymous key is deprioritized; register for
  a free API key, or run your own worker to earn kudos.
- **NSFW**: toggled off by default and content is censored server-side
  unless you explicitly enable it — respect the horde's community rules.
