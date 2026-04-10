"""Skill Review Engine — Phase 3: Auto-review of mission tool calls.

Provides:
    ToolCallLogger  — collects tool call records from AgentDeps.tool_call_log
    ReviewEngine    — processes a log into a structured JSON report
    SkillsUpdateAPI — FastAPI endpoint for receiving and applying review reports

Usage (called from main.py as a background asyncio task):
    from cognibot.review import start_review_api
    asyncio.create_task(start_review_api(config))
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── ToolCallLogger ─────────────────────────────────────────────────────

class ToolCallLogger:
    """Accumulates raw tool call records for post-mission analysis.

    Records are expected to be the dicts produced by the MCP tool proxy
    in agent.py, containing: tool, args, success, latency_ms, result_preview,
    timestamp.
    """

    def __init__(self) -> None:
        self._records: list[dict[str, Any]] = []
        self._mission_id = str(uuid.uuid4())
        self._started_at = time.time()

    def push(self, record: dict[str, Any]) -> None:
        """Append a tool call record."""
        self._records.append(record)

    def flush(self) -> list[dict[str, Any]]:
        """Return and clear the accumulated records."""
        records = list(self._records)
        self._records.clear()
        return records

    @property
    def mission_id(self) -> str:
        return self._mission_id

    def new_mission(self) -> None:
        """Reset for a new conversation / mission."""
        self._records.clear()
        self._mission_id = str(uuid.uuid4())
        self._started_at = time.time()


# ── ReviewEngine ───────────────────────────────────────────────────────

class ReviewEngine:
    """Converts a tool call log into a structured mission review report.

    The report follows this schema:
    {
      "mission_id": "...",
      "generated_at": "ISO8601",
      "duration_s": 42.3,
      "summary": {
        "total_calls": 20,
        "success_rate": 0.85,
        "avg_latency_ms": 1230
      },
      "skills": {
        "navigation": {
          "tools": ["ros2_action_goal"],
          "call_count": 3,
          "success_rate": 0.67,
          "avg_latency_ms": 3200,
          "failed_calls": [...],
          "suggested_thresholds": {}
        },
        ...
      },
      "tool_breakdown": { "ros2_action_goal": {...}, ... }
    }
    """

    # Map tool names → skill category
    TOOL_TO_SKILL: dict[str, str] = {
        "ros2_action_goal":       "navigation",
        "ros2_publish":           "navigation",
        "ros2_cmd_vel_duration":  "navigation",
        "plan_memory_route":      "navigation",
        "ros2_subscribe_once":    "telemetry",
        "ros2_list_topics":       "discovery",
        "ros2_list_services":     "discovery",
        "ros2_list_actions":      "discovery",
        "ros2_list_nodes":        "discovery",
        "ros2_service_call":      "services",
        "ros2_param_get":         "parameters",
        "ros2_param_set":         "parameters",
        "ros2_camera_snapshot":   "perception",
        "ros2_vla_query":         "perception",
        "ros2_depth_distance":    "perception",
        "load_skill_context":     "skills",
        "query_semantic_memory":  "memory",
        "store_memory":           "memory",
    }

    def generate_report(
        self,
        records: list[dict[str, Any]],
        mission_id: str,
        started_at: float,
    ) -> dict[str, Any]:
        """Generate a review report from a list of tool call records."""
        if not records:
            return {
                "mission_id": mission_id,
                "generated_at": _iso8601(time.time()),
                "duration_s": round(time.time() - started_at, 2),
                "summary": {"total_calls": 0, "success_rate": 1.0, "avg_latency_ms": 0},
                "skills": {},
                "tool_breakdown": {},
            }

        # Per-tool aggregation
        tool_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "call_count": 0,
            "successes": 0,
            "latencies": [],
            "failed_calls": [],
        })

        for rec in records:
            tool = rec.get("tool", "unknown")
            s = tool_stats[tool]
            s["call_count"] += 1
            latency = rec.get("latency_ms", 0)
            s["latencies"].append(latency)
            if rec.get("success"):
                s["successes"] += 1
            else:
                s["failed_calls"].append({
                    "timestamp": rec.get("timestamp"),
                    "args":      rec.get("args", {}),
                    "preview":   rec.get("result_preview", "")[:300],
                })

        # Summarize per tool
        tool_breakdown: dict[str, Any] = {}
        for tool, s in tool_stats.items():
            avg_lat = round(sum(s["latencies"]) / len(s["latencies"]), 1) if s["latencies"] else 0
            sr = round(s["successes"] / s["call_count"], 3) if s["call_count"] else 1.0
            tool_breakdown[tool] = {
                "call_count":      s["call_count"],
                "success_rate":    sr,
                "avg_latency_ms":  avg_lat,
                "failed_calls":    s["failed_calls"],
                "suggested_thresholds": _suggest_thresholds(tool, avg_lat, sr),
            }

        # Aggregate by skill category
        skill_agg: dict[str, list[str]] = defaultdict(list)
        for tool in tool_breakdown:
            category = self.TOOL_TO_SKILL.get(tool, "misc")
            skill_agg[category].append(tool)

        skills_report: dict[str, Any] = {}
        for category, tools in skill_agg.items():
            cat_calls = sum(tool_breakdown[t]["call_count"] for t in tools)
            cat_successes = sum(
                int(tool_breakdown[t]["success_rate"] * tool_breakdown[t]["call_count"])
                for t in tools
            )
            cat_latencies = []
            for t in tools:
                cat_latencies.extend([tool_breakdown[t]["avg_latency_ms"]] * tool_breakdown[t]["call_count"])
            cat_avg_lat = round(sum(cat_latencies) / len(cat_latencies), 1) if cat_latencies else 0
            cat_sr = round(cat_successes / cat_calls, 3) if cat_calls else 1.0
            failed = []
            for t in tools:
                failed.extend(tool_breakdown[t]["failed_calls"])

            skills_report[category] = {
                "tools":           tools,
                "call_count":      cat_calls,
                "success_rate":    cat_sr,
                "avg_latency_ms":  cat_avg_lat,
                "failed_calls":    failed,
                "suggested_thresholds": {},
            }

        total = len(records)
        successes = sum(1 for r in records if r.get("success"))
        all_lats = [r.get("latency_ms", 0) for r in records]
        avg_lat = round(sum(all_lats) / len(all_lats), 1) if all_lats else 0

        return {
            "mission_id":    mission_id,
            "generated_at":  _iso8601(time.time()),
            "duration_s":    round(time.time() - started_at, 2),
            "summary": {
                "total_calls":    total,
                "success_rate":   round(successes / total, 3),
                "avg_latency_ms": avg_lat,
            },
            "skills":         skills_report,
            "tool_breakdown": tool_breakdown,
        }


# ── FastAPI Skills Update endpoint ─────────────────────────────────────

def create_review_app(skills_dir: Path) -> Any:
    """Create the FastAPI application for the skill review API.

    Endpoints:
        GET  /health           — liveness check
        POST /skills/review    — accept a review JSON and optionally hot-patch skills
        GET  /skills/reports   — list saved review reports
    """
    try:
        from fastapi import FastAPI, HTTPException, Body
        from fastapi.responses import JSONResponse
    except ImportError:
        logger.warning("fastapi not installed — review API unavailable")
        return None

    app = FastAPI(
        title="CogniBot Skill Review API",
        description="Post-mission review ingestion and skill update endpoint.",
        version="0.1.0",
    )

    reports_dir = skills_dir.parent / "mission_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "cognibot-review-api"}

    @app.post("/skills/review")
    def ingest_review(report: dict = Body(...)) -> JSONResponse:
        """Accept a mission review JSON and persist it to disk."""
        mission_id = report.get("mission_id", str(uuid.uuid4()))
        out_path = reports_dir / f"{mission_id}.json"
        try:
            out_path.write_text(json.dumps(report, indent=2))
            logger.info("Review report saved: %s", out_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Could not save report: {e}")
        return JSONResponse(
            status_code=200,
            content={"status": "saved", "mission_id": mission_id, "path": str(out_path)},
        )

    @app.get("/skills/reports")
    def list_reports() -> JSONResponse:
        """List all saved mission review reports."""
        reports = [
            {"mission_id": p.stem, "path": str(p), "size_bytes": p.stat().st_size}
            for p in sorted(reports_dir.glob("*.json"))
        ]
        return JSONResponse(content={"count": len(reports), "reports": reports})

    return app


async def start_review_api(skills_dir: Path, host: str = "0.0.0.0", port: int = 8765) -> None:
    """Start the review API as a background asyncio task.

    Call via: asyncio.create_task(start_review_api(config.skills_dir))
    """
    try:
        import uvicorn
    except ImportError:
        logger.warning("uvicorn not installed — review API will not start")
        return

    app = create_review_app(skills_dir)
    if app is None:
        return

    uconfig = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(uconfig)
    logger.info("Skill Review API starting on http://%s:%d", host, port)
    try:
        await server.serve()
    except Exception as exc:
        logger.warning("Review API stopped: %s", exc)


# ── Helpers ────────────────────────────────────────────────────────────

def _iso8601(ts: float) -> str:
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"


def _suggest_thresholds(tool: str, avg_latency_ms: float, success_rate: float) -> dict[str, Any]:
    """Generate simple advisory thresholds based on observed performance."""
    suggestions: dict[str, Any] = {}
    if success_rate < 0.8:
        suggestions["alert"] = f"success_rate {success_rate:.0%} below 80% — review error patterns"
    if tool == "ros2_action_goal" and avg_latency_ms > 10000:
        suggestions["planner_frequency"] = "consider increasing Nav2 planner_frequency or costmap resolution"
    if tool in ("ros2_vla_query",) and avg_latency_ms > 15000:
        suggestions["vla_timeout"] = f"avg latency {avg_latency_ms:.0f}ms — consider increasing timeout param"
    return suggestions
