"""Baostock cloud connectivity test for GitHub Actions runners.

Answers one question: can baostock's socket connection to
public-api.baostock.com:10030 be reached from GitHub's datacenter?
This decides whether the IRO daily update can run fully in the cloud
(workflow A) or must run on the user's machine (workflow B).

The script sets a socket timeout so a blocked connection fails fast
instead of hanging the job.
"""
import json
import socket
import sys
import time


def main():
    results = {"login": None, "profit_query": None, "quote_query": None}

    # Default socket timeout so a blocked connection doesn't hang.
    socket.setdefaulttimeout(20)

    try:
        import baostock as bs
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"import": {"ok": False, "detail": repr(exc)[:120]}}, ensure_ascii=False))
        sys.exit(1)

    t0 = time.time()
    try:
        lg = bs.login()
        ok = lg.error_code == "0"
        results["login"] = {"ok": ok, "error_code": lg.error_code, "error_msg": str(lg.error_msg)[:100], "seconds": round(time.time() - t0, 1)}
        if not ok:
            print(json.dumps(results, ensure_ascii=False, indent=2))
            sys.exit(0)

        # Financial query
        t1 = time.time()
        rs = bs.query_profit_data(code="sh.600519", year=2025, quarter=4)
        rows = []
        while (rs.error_code == "0") and rs.next():
            rows.append(rs.get_row_data())
        results["profit_query"] = {
            "ok": rs.error_code == "0",
            "rows": len(rows),
            "error_code": rs.error_code,
            "seconds": round(time.time() - t1, 1),
        }

        # Valuation query
        t2 = time.time()
        rs2 = bs.query_history_k_data_plus(
            "sh.600519", "date,close,peTTM,pbMRQ",
            start_date="2026-08-07", end_date="2026-08-07",
            frequency="d", adjustflag="3",
        )
        rows2 = []
        while (rs2.error_code == "0") and rs2.next():
            rows2.append(rs2.get_row_data())
        results["quote_query"] = {
            "ok": rs2.error_code == "0",
            "rows": len(rows2),
            "error_code": rs2.error_code,
            "seconds": round(time.time() - t2, 1),
        }

        try:
            bs.logout()
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        results["exception"] = repr(exc)[:200]
        results["seconds"] = round(time.time() - t0, 1)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok_count = sum(1 for v in results.values() if isinstance(v, dict) and v.get("ok"))
    print(f"\n=== SUMMARY: {ok_count}/3 checks ok ===")


if __name__ == "__main__":
    main()
