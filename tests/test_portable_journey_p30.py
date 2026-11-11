"""P30 end-to-end synthetic customer journey in the actual portable .pyz.

Rebuilds EAI from source without external dependencies. All user input is
synthetic; no browser, real Ollama, customer files, network hosts or payment.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from scripts.build_portable import build_portable


ROOT=Path(__file__).resolve().parents[1]


class PortableJourneyP30Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=tempfile.TemporaryDirectory()
        cls.bundle=Path(cls.out.name)/"eai-portable.pyz"
        cls.built=build_portable(ROOT,cls.bundle)

    @classmethod
    def tearDownClass(cls):
        cls.out.cleanup()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.csv=self.root/"metrics.csv"
        self.csv.write_text(
            "ads,sales,note\n"
            "1,2,PRIVATE_VALUE_999\n2,4,retail\n3,6,c\n"
            "4,8,d\n5,10,e\n6,12,f\n7,14,g\n8,16,h\n",
            encoding="utf-8"
        )
        self.before=self.root/"before.csv"
        self.after=self.root/"after.csv"
        self.before.write_text("amount\n"+"\n".join(str(i) for i in range(1,12))+"\n")
        self.after.write_text("amount\n"+"\n".join(str(i+20) for i in range(1,12))+"\n")

    def run_eai(self,*args,expect=0):
        result=subprocess.run(
            [sys.executable,str(self.bundle),*args],
            capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,expect,result.stderr+"\n"+result.stdout[:1000])
        return result

    def make_approved(self):
        advice=json.loads(self.run_eai(
            "advise-csv","--root",str(self.root),"--source","metrics.csv","--json").stdout)
        self.assertEqual(advice["status"],"DRAFT_READY")
        self.assertNotIn("PRIVATE_VALUE_999",json.dumps(advice))
        goal=self.root/"relation.json"
        goal.write_text(json.dumps(advice["drafts"][0]["goal"]),encoding="utf-8")
        manifest=json.loads(self.run_eai(
            "make-manifest","--mode","batch","--root",str(self.root),
            "--goal","relation=relation.json").stdout)
        mf=self.root/"batch.json"
        mf.write_text(json.dumps(manifest),encoding="utf-8")
        suggestion=json.loads(self.run_eai(
            "select-goal","--manifest",str(mf),
            "--request","relation","--json").stdout)
        self.assertEqual(suggestion["selected"]["id"],"relation")
        return goal,mf,suggestion

    def test_zip_reproducible_exact_build_sha(self):
        second=self.root/"again.pyz"
        other=build_portable(ROOT,second)
        self.assertEqual(other["sha256"],self.built["sha256"])
        self.assertEqual(hashlib.sha256(self.bundle.read_bytes()).hexdigest(),
                         self.built["sha256"])

    def test_quick_csv_and_text_from_packaged_code(self):
        r=json.loads(self.run_eai(
            "quick-goal","--kind","csv_relationships","--root",str(self.root),
            "--source","metrics.csv","--columns","ads","sales","--json").stdout)
        self.assertEqual(r["status"],"AGREE")
        self.assertEqual(r["verification"]["status"],"PASS")
        self.assertNotIn("PRIVATE_VALUE_999",json.dumps(r))
        (self.root/"manual.md").write_text(
            "risk mitigation is documented\nPRIVATE_TOKEN_7334\n",encoding="utf-8")
        result=json.loads(self.run_eai(
            "quick-goal","--kind","local_evidence_search","--root",str(self.root),
            "--sources","manual.md","--terms","risk","mitigation","--json").stdout)
        self.assertEqual(result["status"],"AGREE")
        self.assertNotIn("PRIVATE_TOKEN_7334",json.dumps(result))

    def test_full_advisor_manifest_select_approve_report(self):
        source_before=self.csv.read_bytes()
        goal,mf,selection=self.make_approved()
        approved=json.loads(self.run_eai(
            "run-approved","--manifest",str(mf),"--id","relation",
            "--manifest-sha256",selection["manifest"]["sha256"],
            "--goal-sha256",selection["selected"]["sha256"],
            "--json").stdout)
        self.assertEqual(approved["status"],"AGREE")
        self.assertEqual(approved["receipt"]["verification"]["status"],"PASS")
        html=self.run_eai("export-report",str(goal),"--format","html").stdout
        self.assertIn("<!doctype html>",html)
        self.assertIn("Content-Security-Policy",html)
        self.assertNotIn("PRIVATE_VALUE_999",html)
        self.assertEqual(self.csv.read_bytes(),source_before)

    def test_packaged_shift_conflict_receipt_and_no_mutation(self):
        goal=self.root/"shift.json"
        goal.write_text(json.dumps({
            "version":1,"kind":"csv_distribution_shift",
            "goal":"Compare synthetic cohorts","baseline":"before.csv",
            "current":"after.csv","encoding":"utf-8-sig",
            "columns":["amount"],"min_rows":5,"threshold":"2"
        }),encoding="utf-8")
        a,b=self.before.read_bytes(),self.after.read_bytes()
        output=json.loads(self.run_eai(
            "solve-goal",str(goal),"--json",expect=2).stdout)
        self.assertEqual(output["status"],"CONFLICT")
        self.assertEqual(output["verification"]["status"],"PASS")
        self.assertEqual((self.before.read_bytes(),self.after.read_bytes()),(a,b))

    def test_qwen_fake_loopback_input_only_never_auto_runs(self):
        goal,mf,selection=self.make_approved()
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw=self.rfile.read(int(self.headers["Content-Length"]))
                received.append(json.loads(raw.decode("utf-8")))
                payload=json.dumps({"message":{
                    "content":json.dumps({"version":1,"selected_id":"relation"})
                }}).encode()
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                self.send_header("Content-Length",str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self,*args):
                pass
        server=HTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            output=json.loads(self.run_eai(
                "--ollama-url",f"http://127.0.0.1:{server.server_port}",
                "select-goal","--manifest",str(mf),"--request","analyze the situation",
                "--qwen-select","--json").stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.assertEqual(output["method"],"LOCAL_MODEL_INPUT_ONLY")
        self.assertEqual(output["selected"]["id"],"relation")
        self.assertTrue(output["requires_explicit_execution"])
        self.assertEqual(len(received),1)
        query=json.dumps(received[0])
        self.assertNotIn("PRIVATE_VALUE_999",query)
        self.assertNotIn("metrics.csv",query)
        self.assertNotIn('"sha256"',query)

    def test_manifest_changed_after_suggestion_blocks_approval(self):
        goal,mf,selected=self.make_approved()
        mf.write_text(mf.read_text()+" ")
        p=self.run_eai(
            "run-approved","--manifest",str(mf),"--id","relation",
            "--manifest-sha256",selected["manifest"]["sha256"],
            "--goal-sha256",selected["selected"]["sha256"],expect=1)
        self.assertIn("EAI APPROVAL ERROR",p.stderr)


if __name__=="__main__":
    unittest.main()
