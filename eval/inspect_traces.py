"""Inspect Langfuse traces from the eval run."""

import json
import os
import sys
from datetime import datetime
from urllib.request import Request, urlopen
from base64 import b64encode


def api(path: str) -> dict:
    host = os.environ["LANGFUSE_HOST"]
    pk = os.environ["LANGFUSE_PUBLIC_KEY"]
    sk = os.environ["LANGFUSE_SECRET_KEY"]
    creds = b64encode(f"{pk}:{sk}".encode()).decode()
    req = Request(f"{host}/api/public{path}", headers={"Authorization": f"Basic {creds}"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def get_traces(name: str = None, limit: int = 50) -> list[dict]:
    url = f"/traces?limit={limit}"
    if name:
        url += f"&name={name}"
    return api(url).get("data", [])


def get_observations(trace_id: str) -> list[dict]:
    return api(f"/observations?traceId={trace_id}&limit=50").get("data", [])


def fmt_output(out) -> str:
    if isinstance(out, str):
        return out[:120]
    if isinstance(out, dict):
        return json.dumps(out)[:120]
    return str(out)[:120] if out else ""


def inspect_trace(trace: dict):
    inp = trace.get("input") or {}
    msg = inp.get("message", "")[:70] if isinstance(inp, dict) else str(inp)[:70]
    lat = trace.get("latency", 0)
    cost = trace.get("totalCost", 0)
    print(f"\n{'='*80}")
    print(f"MSG: {msg}")
    print(f"ID:  {trace['id']}  latency={lat}s  cost=${cost:.4f}")

    obs = get_observations(trace["id"])
    obs.sort(key=lambda x: x.get("startTime", ""))

    for o in obs:
        name = o.get("name") or "?"
        otype = o.get("type") or "?"
        model = o.get("model") or ""

        latency = ""
        if o.get("startTime") and o.get("endTime"):
            s = datetime.fromisoformat(o["startTime"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(o["endTime"].replace("Z", "+00:00"))
            latency = f"{(e-s).total_seconds():.1f}s"

        meta = o.get("metadata") or {}
        pipe = meta.get("pipeline", "")
        step = meta.get("step_id", "")
        tool = meta.get("tool", "")
        stream = meta.get("stream", "")

        parts = [f"{otype}:{name}"]
        if model:
            parts.append(f"model={model}")
        if pipe:
            parts.append(f"pipe={pipe}")
        if step:
            parts.append(f"step={step}")
        if tool:
            parts.append(f"tool={tool}")
        if latency:
            parts.append(latency)

        print(f"  {' | '.join(parts)}")

        out = o.get("output")
        if out:
            print(f"    -> {fmt_output(out)}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "chat"

    if mode == "chat":
        traces = get_traces("chat.stream_response", limit=50)
        print(f"Chat traces: {len(traces)}")
        for t in traces:
            inspect_trace(t)

    elif mode == "jobs":
        # Get all job traces
        for job_name in ["job.process_conversation", "job.process_graph"]:
            traces = get_traces(job_name, limit=20)
            print(f"\n{job_name}: {len(traces)} traces")
            for t in traces[:5]:
                inspect_trace(t)

    elif mode == "summary":
        # Summary of all trace types
        all_traces = get_traces(limit=100)
        by_name = {}
        for t in all_traces:
            name = t.get("name", "unknown")
            by_name.setdefault(name, []).append(t)
        print(f"Total traces: {len(all_traces)}")
        for name, tl in sorted(by_name.items()):
            lats = [t.get("latency", 0) for t in tl if t.get("latency")]
            avg_lat = sum(lats) / len(lats) if lats else 0
            costs = [t.get("totalCost", 0) for t in tl]
            total_cost = sum(costs)
            print(f"  {name:40} count={len(tl):3}  avg_lat={avg_lat:.1f}s  cost=${total_cost:.4f}")

    elif mode.startswith("trace:"):
        trace_id = mode.split(":", 1)[1]
        trace = api(f"/traces/{trace_id}")
        inspect_trace(trace)

    else:
        print(f"Usage: {sys.argv[0]} [chat|jobs|summary|trace:<id>]")


if __name__ == "__main__":
    main()
