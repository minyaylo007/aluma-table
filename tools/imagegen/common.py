"""Shared plumbing for the imagegen pipeline: paths, Bedrock invocation, call log, budget cap.

Every Bedrock invocation (successful or not) goes through `invoke()` and is appended to
<IMAGEGEN_DIR>/CALLS.jsonl. The hard cap is BUDGET_CALLS; once reached, invoke() refuses.

Pipeline directory: env `IMAGEGEN_DIR`, default `furniture/assets-src/product/imagegen/`
(candidates/, final/ and CALLS.jsonl live under it). The September 2026 rounds were run with
`IMAGEGEN_DIR=../night/imagegen` (relative to furniture/): set it to reproduce round2.py / round3.py /
encode.py on those files. Budget: env `IMAGEGEN_BUDGET`, default 70 calls.
"""
import base64, datetime, io, json, os, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parents[2]            # furniture/
BASE = pathlib.Path(os.environ.get("IMAGEGEN_DIR") or (ROOT / "assets-src" / "product" / "imagegen"))
if not BASE.is_absolute():
    BASE = (ROOT / BASE).resolve()
NIGHT = BASE                                                  # old name, kept for callers
CANDIDATES = BASE / "candidates"
FINAL = BASE / "final"
CALLS = BASE / "CALLS.jsonl"
PHOTOS = ROOT / "site" / "assets" / "photos"

REGION = "us-east-1"
BUDGET_CALLS = int(os.environ.get("IMAGEGEN_BUDGET") or 70)
EST_USD_PER_CALL = 0.10

MODELS = {
    "structure": "us.stability.stable-image-control-structure-v1:0",
    "recolor":   "us.stability.stable-image-search-recolor-v1:0",
    "erase":     "us.stability.stable-image-erase-object-v1:0",
    "replace":   "us.stability.stable-image-search-replace-v1:0",
    "inpaint":   "us.stability.stable-image-inpaint-v1:0",
    "rembg":     "us.stability.stable-image-remove-background-v1:0",
    "upscale":   "us.stability.stable-conservative-upscale-v1:0",
    "upscale-fast": "us.stability.stable-fast-upscale-v1:0",
    "style":     "us.stability.stable-image-style-guide-v1:0",
    "outpaint":  "us.stability.stable-outpaint-v1:0",
}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_calls():
    if not CALLS.exists():
        return []
    out = []
    for line in CALLS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def calls_used():
    return sum(1 for r in read_calls() if r.get("type") == "call")


def append_call(rec):
    BASE.mkdir(parents=True, exist_ok=True)
    with CALLS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rewrite_calls(recs):
    tmp = CALLS.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    tmp.replace(CALLS)


def grade(output_file, verdict, reason):
    """Mark the call that produced `output_file` accepted/rejected (in place)."""
    name = pathlib.Path(output_file).name
    recs = read_calls()
    hit = False
    for r in recs:
        if r.get("type") == "call" and r.get("output") and pathlib.Path(r["output"]).name == name:
            r["verdict"] = verdict
            r["reason"] = reason
            r["graded_at"] = now_iso()
            hit = True
    if not hit:
        raise SystemExit(f"no call record for {output_file}")
    rewrite_calls(recs)


def img_to_b64(im, fmt="PNG"):
    buf = io.BytesIO()
    im.save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def b64_to_bytes(s):
    return base64.b64decode(s)


def summarize_params(body):
    """Log-safe copy of a request body (no base64 blobs)."""
    out = {}
    for k, v in body.items():
        if k in ("image", "mask") or (isinstance(v, str) and len(v) > 5000):
            out[k] = f"<{len(v)} chars>"
        else:
            out[k] = v
    return out


def invoke(model_key, body, output_path, note="", dry_run=False):
    """Call Bedrock, save the first returned image to output_path, log the call.

    Returns the parsed response dict (images stripped) or raises. Every attempt, including
    failures, counts against BUDGET_CALLS.
    """
    used = calls_used()
    if used >= BUDGET_CALLS:
        raise SystemExit(f"BUDGET CAP: {used}/{BUDGET_CALLS} Bedrock calls already logged; refusing to invoke.")
    model_id = MODELS[model_key]
    rec = {
        "type": "call", "ts": now_iso(), "n": used + 1, "model": model_id, "model_key": model_key,
        "seed": body.get("seed"), "params": summarize_params(body),
        "output": pathlib.Path(output_path).as_posix(), "note": note,
        "verdict": "ungraded", "reason": "", "est_usd": EST_USD_PER_CALL,
    }
    if dry_run:
        print("DRY RUN", json.dumps(rec, ensure_ascii=False, indent=1))
        return None
    import boto3
    from botocore.config import Config
    client = boto3.client("bedrock-runtime", region_name=REGION,
                          config=Config(read_timeout=300, retries={"max_attempts": 1}))
    t0 = time.time()
    try:
        resp = client.invoke_model(modelId=model_id, body=json.dumps(body),
                                   contentType="application/json", accept="application/json")
        data = json.loads(resp["body"].read())
    except Exception as e:  # log and re-raise: failed calls still count
        rec["status"] = "error"
        rec["error"] = str(e)[:600]
        rec["secs"] = round(time.time() - t0, 1)
        append_call(rec)
        raise
    rec["secs"] = round(time.time() - t0, 1)
    imgs = data.get("images") or []
    if not imgs:
        rec["status"] = "no-image"
        rec["response"] = {k: v for k, v in data.items() if k != "images"}
        append_call(rec)
        raise SystemExit(f"no image in response: {rec['response']}")
    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path).write_bytes(b64_to_bytes(imgs[0]))
    rec["status"] = "ok"
    rec["seeds_out"] = data.get("seeds")
    rec["finish_reasons"] = data.get("finish_reasons")
    append_call(rec)
    print(f"[{rec['n']}/{BUDGET_CALLS}] {model_key} seed={body.get('seed')} -> {output_path} ({rec['secs']}s)")
    return {k: v for k, v in data.items() if k != "images"}


def parse_tone_state(path):
    """renders-master/hero-natural-closed.png -> ('hero','natural','closed')"""
    stem = pathlib.Path(path).stem
    parts = stem.split("-")
    view, tone, state = (parts + ["?", "?", "?"])[:3]
    return view, tone, state
