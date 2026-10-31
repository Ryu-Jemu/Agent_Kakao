"""공개 TC 고객별 회원·주문 사전 조회(API-13→API-08, GET만). 결과: tests/logs/customers.json"""
import json, os, re, sys, time, glob
sys.path.insert(0, os.path.dirname(__file__))
import httpx
from probe import BASE, ROOT, token, quote_path

out = {}
tcs = sorted(glob.glob(os.path.join(ROOT, "tests/tc/public/*.md")))
with httpx.Client(timeout=20) as c:
    for p in tcs:
        tid = os.path.basename(p)[:-3]
        txt = open(p, encoding="utf-8").read()
        m = re.search(r"인입 계정: 회원 로그인 · (\S+) · 019-\*\*\*\*-(\d{4})", txt)
        name, last4 = m.group(1), m.group(2)
        h = {"Authorization": f"Bearer {token()}", "X-Aitop100-Test-Case-Id": tid}
        r = c.get(BASE + quote_path(f"/api/members?name={name}"), headers=h)
        mems = r.json() if r.status_code == 200 else []
        mem = [x for x in mems if str(x.get("phone", "")).endswith(last4)]
        rec = {"name": name, "last4": last4, "members_found": len(mems), "member": mem[0] if mem else None, "orders": None}
        if mem:
            r2 = c.get(BASE + f"/api/orders?member_id={mem[0]['member_id']}", headers=h)
            rec["orders"] = r2.json() if r2.status_code == 200 else {"status": r2.status_code}
        out[tid] = rec
        time.sleep(0.4)
json.dump(out, open(os.path.join(ROOT, "tests/logs/customers.json"), "w"), ensure_ascii=False, indent=1)
for tid, rec in out.items():
    mm = rec["member"] or {}
    print(f"== {tid} {rec['name']} {mm.get('member_id')} type={mm.get('member_type')} grade={mm.get('grade')} found={rec['members_found']}")
    for o in rec["orders"] or []:
        its = ",".join(f"{i['sku']}x{i['qty']}@{i['unit_price']}" for i in o.get("items", []))
        print(f"   {o['order_no']} {o['status']} ord={o['ordered_at'][:16]} amt={o['amount']} pay={o['payment_refs']} {its} ship_sched={o.get('ship_scheduled_at')} rf={o['refund_ids']} cr={o['change_request_ids']} addr={o['shipping_address'][:12]} rcpt={o['recipient_name']}")
