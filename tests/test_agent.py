"""The ci: agent — its sandbox, its reading of the answer keys, its vote, and a whole answer against a scripted model.

No model is needed: a stub OpenAI-compatible server replies with fixed programs, so these pin the harness, not a
model's skill. The agent must take the answer shape from the prompt alone — the tests hand it tasks whose grader-side
answer is deliberately wrong, and it must not care.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from constructbench.agent import (Agent, answer_keys, coerce, options_in, parse_tables, run_program, sanity, snap,
                                  tidy, vote)
from constructbench.agent import parse_bullets, parse_texts, prompt_inputs
from constructbench.toolkit import box_gap, box_overlap, cpm, irr, npv, parse_step, pv_annuity, round_half_up, step_args
from constructbench.grading import grade
from constructbench.task import Task


class Stub(BaseHTTPRequestHandler):
    replies: list[str] = []
    seen: list[dict] = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append(body)
        text = Stub.replies.pop(0) if Stub.replies else "```python\nprint(json.dumps({}))\n```"
        out = json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}],
                          "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


def program(d: dict) -> str:
    return "```python\nanswer = " + repr(d) + "\nprint(json.dumps(answer))\n```"


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Stub.replies, Stub.seen = [], []

    def task(self, answer=None):
        return Task.from_json({"id": "t-0", "domain": "estimating", "category": "c", "title": "t", "difficulty": "easy",
                               "prompt": 'Compute it.\nAnswer keys: "area_sq_ft" (number), "complies" (string).',
                               "answer": answer or {"area_sq_ft": 120, "complies": "yes"},
                               "fields": {"area_sq_ft": {"kind": "number", "rel_tol": 0.005, "abs_tol": 0.5},
                                          "complies": {"kind": "text", "rel_tol": 0, "abs_tol": 0}},
                               "meta": {}, "attachments": []})

    # ── pieces ──
    def test_answer_keys_come_from_the_prompt(self):
        self.assertEqual(answer_keys(self.task().prompt), [("area_sq_ft", "number"), ("complies", "string")])

    def test_sandbox_runs_arithmetic_and_the_stdlib(self):
        res, err = run_program("import statistics, datetime\nprint(json.dumps({'m': statistics.mean([2, 4]), "
                               "'d': str(datetime.date(2026, 1, 2) + datetime.timedelta(days=30))}))")
        self.assertEqual(err, "")
        self.assertEqual(res, {"m": 3, "d": "2026-02-01"})

    def test_sandbox_refuses_files_processes_and_network(self):
        for bad in ["import os\nprint(1)", "import subprocess", "open('/etc/passwd')", "__import__('os')",
                    "import socket", "eval('1')", "from pathlib import Path"]:
            res, err = run_program(bad)
            self.assertIsNone(res, bad)
            self.assertTrue(err, bad)

    def test_sandbox_times_out(self):
        res, err = run_program("while True:\n    pass", timeout=2)
        self.assertIsNone(res)
        self.assertIn("longer than", err)

    def test_vote_takes_the_majority_per_field(self):
        got = vote([{"a": 10.0, "b": "yes"}, {"a": 10.004, "b": "no"}, {"a": 99, "b": "yes"}],
                   [("a", "number"), ("b", "string")])
        self.assertEqual(got, {"a": 10.0, "b": "yes"})

    def test_coerce(self):
        self.assertEqual(coerce("$1,250.50", "number"), 1250.5)
        self.assertEqual(coerce(True, "string"), "yes")
        self.assertIsNone(coerce(True, "number"))

    def test_tidy_fixes_units_after_numbers_and_money_strings(self):
        self.assertEqual(tidy("w = 204.0 'ft'"), "w = 204.0  # 'ft'")
        self.assertEqual(tidy("h = 12 ft  # wall"), "h = 12  # ft  # wall")
        self.assertEqual(tidy("c = ['$21,500', \"1,250.5\"]"), "c = [21500, 1250.5]")
        for keep in ["x = 5 if a else 6", "v = float('1,250'.replace(',', ''))", "name = 'Bay 3'", "y = 2 * x  # ft"]:
            self.assertEqual(tidy(keep), keep)
        res, err = run_program("w = 204.0 'ft'\nprint(json.dumps({'a': w * 2}))")
        self.assertEqual((res, err), ({"a": 408.0}, ""))

    def test_answer_keys_keep_types_with_detail(self):
        p = 'Answer keys: "delivery_date" (string YYYY-MM-DD), "ids" (array of strings), "n" (integer).'
        self.assertEqual(answer_keys(p), [("delivery_date", "string"), ("ids", "array"), ("n", "integer")])

    def test_markdown_tables_are_parsed_with_numbers(self):
        p = ("Bids:\n\n| Bidder | Base bid | Markup | Preds |\n|---|---|---|---|\n| Acme | $21,500 | 12% | B, D |\n"
             "| Bolt | (3,000) | 7.5 | — |\n\nAnswer keys: \"x\" (number).")
        self.assertEqual(parse_tables(p), [[{"Bidder": "Acme", "Base bid": 21500, "Markup": 12, "Preds": "B, D"},
                                            {"Bidder": "Bolt", "Base bid": -3000, "Markup": 7.5, "Preds": "—"}]])
        res, err = run_program("print(json.dumps({'s': sum(r['Base bid'] for r in TABLES[0])}))", tables=parse_tables(p))
        self.assertEqual((res, err), ({"s": 18500}, ""))

    def test_toolkit(self):
        r = cpm([{"id": "A", "duration": 10, "preds": "—"}, {"id": "B", "duration": 5, "preds": "A"},
                 {"id": "C", "duration": 3, "preds": "A"}, {"id": "D", "duration": 2, "preds": ["B", "C"]}])
        self.assertEqual(r["duration"], 17)
        self.assertEqual(r["critical"], ["A", "B", "D"])
        self.assertEqual((r["by_id"]["C"]["tf"], r["by_id"]["C"]["ff"]), (2, 2))
        self.assertAlmostEqual(pv_annuity(1000, 0.07, 20), 10594.01, places=2)
        self.assertAlmostEqual(irr([-1000, 600, 600]), 0.1307, places=4)
        self.assertAlmostEqual(npv(0.1, [-100, 110]), 0.0, places=9)
        self.assertEqual((round_half_up(2.5), round_half_up(-2.5), round_half_up(1.005, 2)), (3, -3, 1.01))
        res, _ = run_program("print(json.dumps({'d': cpm([{'id': 'A', 'duration': 4}])['duration']}))")
        self.assertEqual(res, {"d": 4})
        res, err = run_program("print(json.dumps({'d': 1}))", toolkit=False)
        self.assertEqual(res, {"d": 1})

    def test_texts_and_bullets_are_preloaded(self):
        p = ("Codes:\n- Project: ABC\n- Role: A, S\n\nFiles:\n- ABC-1\n- ABC-2\n\n```\n#1=IFCWALL('g',$,'W-1');\n```\n"
             "--- document (OCR text) ---\nTICKET T-5\n--- end ---\nAnswer keys: \"n\" (integer).")
        self.assertEqual(parse_bullets(p), [["Project: ABC", "Role: A, S"], ["ABC-1", "ABC-2"]])
        self.assertEqual(parse_texts(p), ["#1=IFCWALL('g',$,'W-1');", "TICKET T-5"])
        res, err = run_program("print(json.dumps({'n': len(BULLETS[1]), 'w': parse_step(TEXTS[0])['#1']['args'][2]}))",
                               inputs=prompt_inputs(p))
        self.assertEqual((res, err), ({"n": 2, "w": "W-1"}, ""))

    def test_step_parser_and_box_helpers(self):
        self.assertEqual(step_args("'it''s',#5,(#1,#2),$,.ELEMENT.,4.5,IFCLABEL('a,b'),*"),
                         ["it's", "#5", ["#1", "#2"], None, "ELEMENT", 4.5, "IFCLABEL('a,b')", None])
        e = parse_step("#10=IFCQUANTITYVOLUME('NetVolume',$,$,6.997,$);\n#11=IFCELEMENTQUANTITY('g',#5,'Qto',$,$,(#10));")
        self.assertEqual(e["#11"]["args"][5], ["#10"])
        self.assertEqual(e["#10"]["args"][3], 6.997)
        self.assertEqual(box_overlap((0, 100, 0, 100, 0, 100), (50, 150, 0, 100, 0, 100)), [50, 100, 100])
        self.assertEqual(box_gap((0, 100, 0, 100, 0, 100), (130, 200, 140, 200, 0, 100)), 50.0)
        self.assertEqual(box_gap((0, 100, 0, 100, 0, 100), (100, 200, 0, 100, 0, 100)), 0.0)

    def test_the_toolkit_solves_a_generated_ifc_task(self):
        from constructbench import registry
        for t in registry.build(seed=5, per_family=4, families=["ifc_quantities"]):
            code = """e = parse_step(TEXTS[0])
st = {k: v['args'][2] for k, v in e.items() if v['type'] == 'IFCBUILDINGSTOREY'}
lvl, q = {}, {}
for k, v in e.items():
    if v['type'] == 'IFCRELCONTAINEDINSPATIALSTRUCTURE':
        for x in v['args'][4]: lvl[x] = st[v['args'][5]]
    if v['type'] == 'IFCRELDEFINESBYPROPERTIES':
        qs = {e[r]['args'][0]: e[r]['args'][3] for r in e[v['args'][5]]['args'][5]}
        for x in v['args'][4]: q[x] = qs
walls = [k for k, v in e.items() if v['type'] == 'IFCWALL']
print(json.dumps({'v': sum(q[w]['NetVolume'] for w in walls if lvl[w] == 'Level 2'),
                  'd': sum(1 for k, v in e.items() if v['type'] == 'IFCDOOR' and lvl[k] == 'Level 1')}))"""
            res, err = run_program(code, inputs=prompt_inputs(t.prompt))
            self.assertEqual(err, "")
            self.assertAlmostEqual(res["v"], t.answer["level2_wall_net_volume_m3"], places=3)
            self.assertEqual(res["d"], t.answer["level1_door_count"])

    def test_choice_answers_snap_to_the_offered_options(self):
        p = 'Which is lower ("A" or "B")? Must the site "import" or "export"?\nAnswer keys: "lower" (string), "io" (string).'
        o = options_in(p, answer_keys(p))
        self.assertEqual(o, ["A", "B", "import", "export"])
        self.assertEqual([snap(v, o) for v in ["Option A", " b ", "Import soil", "neither", "A or B"]],
                         ["A", "B", "import", "neither", "A or B"])

    def test_integers_and_lists_are_coerced_and_list_order_does_not_split_a_vote(self):
        self.assertEqual(coerce(59.0000001, "integer"), 59)
        self.assertEqual(coerce(59.4, "integer"), 59.4)
        self.assertIsNone(coerce(float("nan"), "number"))
        self.assertEqual(coerce("A, B", "array"), ["A", "B"])
        got = vote([{"x": ["B", "A"]}, {"x": ["C"]}, {"x": ["A", "B"]}], [("x", "array")])
        self.assertEqual(got, {"x": ["B", "A"]})

    # ── whole answers ──
    def test_a_correct_program_is_graded_correct(self):
        Stub.replies = [program({"area_sq_ft": 120.0, "complies": "yes"})] * 3
        r = Agent("m", self.url).answer(self.task())
        self.assertTrue(r.ok)
        self.assertTrue(grade(self.task(), r.text).correct, r.text)

    def test_an_error_is_fed_back_and_fixed(self):
        Stub.replies = ["```python\nprint(json.dumps({'area_sq_ft': 1/0}))\n```",
                        program({"area_sq_ft": 120, "complies": "yes"})] + [program({"area_sq_ft": 120, "complies": "yes"})] * 2
        r = Agent("m", self.url).answer(self.task())
        self.assertTrue(grade(self.task(), r.text).correct)
        self.assertIn("ZeroDivisionError", json.dumps(Stub.seen[1]["messages"][-1]))
        self.assertIn("A divisor is zero", json.dumps(Stub.seen[1]["messages"][-1]))

    def test_tables_and_toolkit_are_described_to_the_model(self):
        t = self.task()
        t.prompt = "| ID | Duration |\n|---|---|\n| A | 3 |\n" + t.prompt
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 3
        Agent("m", self.url).answer(t)
        user = Stub.seen[0]["messages"][1]["content"]
        self.assertIn("TABLES[0]: 1 rows", user)
        self.assertIn("cpm(activities)", user)
        Stub.seen = []
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 3
        Agent("m", self.url, tables=False, toolkit=False).answer(t)
        self.assertNotIn("TABLES", Stub.seen[0]["messages"][1]["content"])

    def test_one_bad_program_is_outvoted(self):
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"}), program({"area_sq_ft": 999, "complies": "no"}),
                        program({"area_sq_ft": 120, "complies": "yes"})]
        self.assertTrue(grade(self.task(), Agent("m", self.url).answer(self.task()).text).correct)

    def test_the_grader_side_answer_is_never_used(self):
        # Same model output, different "true" answer: the agent's reply must not change.
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 3
        a = Agent("m", self.url).answer(self.task()).text
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 3
        b = Agent("m", self.url).answer(self.task(answer={"area_sq_ft": -1, "complies": "no"})).text
        self.assertEqual(a, b)

    def test_sanity_flags_fractions_negative_counts_and_non_finite(self):
        keys = [("bundles", "integer"), ("ties", "integer"), ("cost", "number")]
        self.assertEqual(sanity({"bundles": 996, "ties": 3.0, "cost": -5.5}, keys), [])
        issues = sanity({"bundles": 995.6, "ties": -2, "cost": float("inf")}, keys)
        self.assertEqual(len(issues), 3)
        self.assertIn("math.ceil", issues[0])

    def test_an_implausible_answer_is_sent_back_once(self):
        task =Task.from_json({"id": "t-1", "domain": "estimating", "category": "c", "title": "t", "difficulty": "easy",
                               "prompt": 'Order bundles.\nAnswer keys: "bundles" (integer).', "answer": {"bundles": 996},
                               "fields": {"bundles": {"kind": "integer", "rel_tol": 0, "abs_tol": 0}},
                               "meta": {}, "attachments": []})
        Stub.replies = [program({"bundles": 995.63}), program({"bundles": 996})] + [program({"bundles": 996})] * 2
        r = Agent("m", self.url).answer(task)
        self.assertTrue(grade(task, r.text).correct, r.text)
        self.assertIn("whole number", json.dumps(Stub.seen[1]["messages"][-1]))

    def test_reference_cards_and_units_reach_the_model_and_can_be_turned_off(self):
        t = self.task()
        t.prompt = 'Compute the TRIR on 200,000 hours.\nAnswer keys: "trir" (number), "slope_percent" (number).'
        Stub.replies = [program({"trir": 1, "slope_percent": 2})] * 3
        Agent("m", self.url).answer(t)
        user = Stub.seen[0]["messages"][1]["content"]
        self.assertIn("incident rates:", user)
        self.assertIn('"slope_percent" (number, a percent', user)
        Stub.seen = []
        Stub.replies = [program({"trir": 1, "slope_percent": 2})] * 3
        Agent("m", self.url, knowledge=False).answer(t)
        self.assertNotIn("Construction reference", Stub.seen[0]["messages"][1]["content"])

    def test_a_split_with_no_majority_samples_more(self):
        Stub.replies = [program({"area_sq_ft": 100, "complies": "yes"}), program({"area_sq_ft": 110, "complies": "yes"}),
                        program({"area_sq_ft": 120, "complies": "yes"}), program({"area_sq_ft": 120, "complies": "yes"})]
        r = Agent("m", self.url).answer(self.task())
        self.assertEqual(len(Stub.seen), 4)
        self.assertTrue(grade(self.task(), r.text).correct, r.text)

    def test_an_agreed_answer_does_not_sample_more(self):
        Stub.replies = [program({"area_sq_ft": 120, "complies": "yes"})] * 5
        Agent("m", self.url).answer(self.task())
        self.assertEqual(len(Stub.seen), 3)

    def test_no_program_runs_falls_back_to_a_direct_answer(self):
        Stub.replies = ["no code here"] * 9 + ['Area is 120.\nANSWER: {"area_sq_ft": 120, "complies": "yes", "x": 1}']
        r = Agent("m", self.url).answer(self.task())
        self.assertIn("Answered directly", r.text)
        self.assertTrue(grade(self.task(), r.text).correct, r.text)

    def test_nothing_runs_still_gives_an_answer_line(self):
        Stub.replies = ["no code here"] * 12
        r = Agent("m", self.url).answer(self.task())
        self.assertIn("ANSWER: {}", r.text)


if __name__ == "__main__":
    unittest.main()
