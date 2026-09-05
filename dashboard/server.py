import csv
import json
import mimetypes
import os
import subprocess
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
OUT_DIR = os.path.join(PROJECT_ROOT, "out")
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
STATIC_DIR = os.path.join(BASE_DIR, "static")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    from generate_data import build_all
    from reason_codes import REASON_CODES, ARTIFACTS
    from representment import collect_evidence, build_packet, verify_citations
except ImportError as err:
    print(f"Warning: Could not import core ML modules: {err}")

class DisputeCache:
    def __init__(self):
        self.test_df = None
        self.audit_log = []
        self.results = {}
        self.thresholds = []
        self.reload()

    def reload(self):
        audit_file = os.path.join(OUT_DIR, "audit_log.json")
        results_file = os.path.join(OUT_DIR, "results.json")
        if not os.path.exists(audit_file) or not os.path.exists(results_file):
            print("Running initial evaluation batch...")
            cmd = [sys.executable, os.path.join(SRC_DIR, "run_batch.py")]
            subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)

        if os.path.exists(audit_file):
            with open(audit_file, "r", encoding="utf-8") as f:
                self.audit_log = json.load(f)

        if os.path.exists(results_file):
            with open(results_file, "r", encoding="utf-8") as f:
                self.results = json.load(f)

        sweep_file = os.path.join(OUT_DIR, "threshold_sweep.csv")
        if os.path.exists(sweep_file):
            with open(sweep_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                self.thresholds = [r for r in reader]

        try:
            _, test, _ = build_all()
            self.test_df = test.set_index("dispute_id", drop=False)
        except Exception as e:
            print(f"Notice: Synthetic test data generation deferred: {e}")

CACHE = DisputeCache()


class DashboardHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            return self.serve_static("index.html")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):]
            return self.serve_static(rel_path)
        elif path == "/api/metrics":
            return self.serve_metrics()
        elif path == "/api/disputes":
            return self.serve_disputes(parsed.query)
        elif path == "/api/packet":
            return self.serve_packet(parsed.query)
        elif path == "/api/threshold-sweep":
            return self.serve_threshold_sweep()
        elif path == "/api/reason-codes":
            return self.serve_reason_codes()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "File or endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/run-batch":
            self.run_batch_script()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def serve_static(self, rel_path):
        clean_path = os.path.normpath(rel_path).lstrip(os.sep)
        full_path = os.path.join(STATIC_DIR, clean_path)

        if not os.path.exists(full_path) or os.path.isdir(full_path):
            self.send_error(HTTPStatus.NOT_FOUND, f"Static asset not found: {rel_path}")
            return

        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            with open(full_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Error reading asset: {e}")

    def serve_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def serve_metrics(self):
        in_dist_metrics = CACHE.results.get("metrics", {}).get("in_dist", {})
        best_t = CACHE.results.get("best_threshold", {})
        policies = CACHE.results.get("policies", {})

        total_disputes = len(CACHE.audit_log)
        total_at_risk = sum(d.get("amount_inr", 0) for d in CACHE.audit_log)

        fight_count = sum(1 for d in CACHE.audit_log if d.get("decision") == "fight")
        concede_count = sum(1 for d in CACHE.audit_log if d.get("decision") == "concede")
        escalate_count = sum(1 for d in CACHE.audit_log if d.get("decision") == "escalate")

        ev_policy_stats = policies.get("in-dist", {}).get("EV + novelty shrinkage", {})

        response = {
            "summary": {
                "total_disputes": total_disputes,
                "amount_at_risk": total_at_risk,
                "net_pnl": ev_policy_stats.get("net_pnl", 0),
                "gross_recovered": ev_policy_stats.get("gross_recovered", 0),
                "recovery_rate": ev_policy_stats.get("recovery_rate", 0),
                "fight_count": fight_count,
                "concede_count": concede_count,
                "escalate_count": escalate_count,
                "fight_win_rate": ev_policy_stats.get("fight_win_rate", 0),
                "model_pr_auc": in_dist_metrics.get("pr_auc", 0),
                "model_roc_auc": in_dist_metrics.get("roc_auc", 0),
                "model_precision": in_dist_metrics.get("precision", 0),
                "model_recall": in_dist_metrics.get("recall", 0),
                "optimal_threshold": best_t.get("threshold", 0.32),
            },
            "policies": policies,
            "metrics": CACHE.results.get("metrics", {}),
        }
        self.serve_json(response)

    def serve_disputes(self, query_str):
        qs = parse_qs(query_str)
        items = list(CACHE.audit_log)

        decision = qs.get("decision", [None])[0]
        if decision and decision.lower() != "all":
            items = [d for d in items if d.get("decision", "").lower() == decision.lower()]

        network = qs.get("network", [None])[0]
        if network and network.lower() != "all":
            items = [d for d in items if d.get("network", "").lower() == network.lower()]

        has_gap = qs.get("has_gap", [None])[0]
        if has_gap == "true":
            items = [d for d in items if len(d.get("critical_gaps", [])) > 0]
        elif has_gap == "false":
            items = [d for d in items if len(d.get("critical_gaps", [])) == 0]

        novel = qs.get("novel", [None])[0]
        if novel == "true":
            items = [d for d in items if d.get("novelty_flag") is True]

        q = qs.get("q", [None])[0]
        if q:
            q_clean = q.lower().strip()
            items = [
                d for d in items
                if q_clean in d.get("dispute_id", "").lower()
                or q_clean in d.get("reason_code", "").lower()
                or q_clean in d.get("network", "").lower()
            ]

        sort_by = qs.get("sort_by", ["dispute_id"])[0]
        order = qs.get("order", ["asc"])[0]
        reverse = order.lower() == "desc"

        def get_sort_key(x):
            val = x.get(sort_by, 0)
            if val is None:
                return 0
            return val

        if sort_by in ["amount_inr", "p_win_adjusted", "expected_value", "breakeven_p", "days_remaining", "artifacts_found"]:
            items.sort(key=get_sort_key, reverse=reverse)
        elif sort_by in ["dispute_id", "decision", "network", "reason_code"]:
            items.sort(key=lambda x: str(x.get(sort_by, "")), reverse=reverse)

        total_count = len(items)

        page = int(qs.get("page", [1])[0])
        page_size = int(qs.get("page_size", [50])[0])
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = items[start:end]

        self.serve_json({
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total_count + page_size - 1) // page_size),
            "disputes": paginated_items,
        })

    def serve_packet(self, query_str):
        qs = parse_qs(query_str)
        dispute_id = qs.get("id", [None])[0]
        if not dispute_id:
            return self.serve_json({"error": "Missing dispute id"}, status=HTTPStatus.BAD_REQUEST)

        meta = next((d for d in CACHE.audit_log if d.get("dispute_id") == dispute_id), None)
        if not meta:
            return self.serve_json({"error": f"Dispute not found: {dispute_id}"}, status=HTTPStatus.NOT_FOUND)

        packet_text = ""
        evidence_dict = {}
        reason_info = {}

        rc_code = meta.get("reason_code")
        if rc_code in REASON_CODES:
            rc = REASON_CODES[rc_code]
            reason_info = {
                "code": rc.code,
                "network": rc.network,
                "title": rc.title,
                "category": rc.category,
                "required": rc.required,
                "supporting": rc.supporting,
                "deadline_days": rc.response_deadline_days,
                "base_win_rate": rc.base_win_rate,
            }

        if CACHE.test_df is not None and dispute_id in CACHE.test_df.index:
            row = CACHE.test_df.loc[dispute_id]
            evidence_dict = collect_evidence(row)
            packet_text = build_packet(
                row, evidence_dict, meta.get("p_win_adjusted", 0.0), meta.get("decision", "concede")
            )
            violations = verify_citations(packet_text, evidence_dict)
        else:
            sample_packet_file = os.path.join(OUT_DIR, "sample_packet.txt")
            if os.path.exists(sample_packet_file):
                with open(sample_packet_file, "r", encoding="utf-8") as f:
                    packet_text = f.read()
            violations = []

        all_artifact_defs = ARTIFACTS

        self.serve_json({
            "dispute": meta,
            "reason_info": reason_info,
            "evidence": evidence_dict,
            "packet_text": packet_text,
            "citations_valid": len(violations) == 0,
            "citation_violations": violations,
            "artifact_definitions": all_artifact_defs,
        })

    def serve_threshold_sweep(self):
        self.serve_json({"thresholds": CACHE.thresholds})

    def serve_reason_codes(self):
        data = {}
        for code, rc in REASON_CODES.items():
            data[code] = {
                "code": rc.code,
                "network": rc.network,
                "title": rc.title,
                "category": rc.category,
                "required": rc.required,
                "supporting": rc.supporting,
                "deadline_days": rc.response_deadline_days,
                "base_win_rate": rc.base_win_rate,
            }
        self.serve_json({"reason_codes": data, "artifact_definitions": ARTIFACTS})

    def run_batch_script(self):
        try:
            cmd = [sys.executable, os.path.join(SRC_DIR, "run_batch.py")]
            res = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                CACHE.reload()
                self.serve_json({"success": True, "output": res.stdout[-800:]})
            else:
                self.serve_json({"success": False, "error": res.stderr}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
        except Exception as e:
            self.serve_json({"success": False, "error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def run_server(port=8080, open_browser=True):
    for p in range(port, port + 10):
        try:
            httpd = ThreadingHTTPServer(("", p), DashboardHandler)
            url = f"http://localhost:{p}"
            print(f"Chargeback Responder Dashboard running at {url}")
            if open_browser:
                import threading
                import time
                import webbrowser

                def _open():
                    time.sleep(0.5)
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass

                threading.Thread(target=_open, daemon=True).start()
                print("Opening dashboard in your default browser...")
            print("Press Ctrl+C to stop.")
            httpd.serve_forever()
            break
        except OSError:
            continue

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
