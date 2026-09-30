import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('engine', Path(__file__).parents[1] / 'independent_work' / 'engine.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class WorkEngineTests(unittest.TestCase):
    def event(self, state, now, kind='heartbeat', visible=True, owner='tab1', **extra):
        return engine.advance(state, dict(type=kind, client_id=owner, visible=visible, **extra), now)

    def start(self, minutes=1):
        state = engine.new_state(minutes, 182507)
        self.event(state, 100000, 'hello')
        return state

    def test_fractional_duration(self):
        for minutes, seconds in [(35.4, 2124), (32.2, 1932), (21.36, 1281.6)]:
            self.assertEqual(engine.new_state(minutes, 1)['target_ms'], round(seconds * 1000))

    def test_hidden_time_and_reconnect_not_credited(self):
        s = self.start()
        self.event(s, 101000)
        self.event(s, 101500, 'visibility', visible=False)
        self.event(s, 102500, visible=False)
        self.event(s, 103500, 'visibility', visible=True)
        self.event(s, 104500)
        self.assertEqual(s['active_ms'], 2500)
        self.event(s, 204500)
        self.assertEqual(s['active_ms'], 2500)
        self.event(s, 205500)
        self.assertEqual(s['active_ms'], 3500)

    def test_refresh_round_trip_preserves_state(self):
        s = self.start()
        self.event(s, 101000)
        s = json.loads(json.dumps(s))
        self.event(s, 900000, 'hello', owner='newtab')
        self.assertEqual(s['active_ms'], 1000)
        self.assertFalse(self.event(s, 901000, owner='tab1'))
        self.event(s, 901000, owner='newtab')
        self.assertEqual(s['active_ms'], 2000)

    def first_prompt(self, state):
        now = 100000
        while not state['prompt']:
            now += 1000
            self.event(state, now)
        return now

    def test_correct_and_duplicate_response(self):
        s = self.start()
        now = self.first_prompt(s)
        p = s['prompt'].copy()
        self.event(s, now + 100, 'response', prompt_id=p['id'], response=p['answer'])
        self.event(s, now + 200, 'response', prompt_id=p['id'], response=p['answer'])
        self.assertEqual((s['correct'], s['answered'], s['total']), (1, 1, 1))
        self.assertEqual(engine.metrics(s)['accuracy_rate'], 1)

    def test_wrong_answer_and_missed_deadline(self):
        s = self.start(3)
        now = self.first_prompt(s)
        p = s['prompt']
        wrong = 'J' if p['answer'] == 'F' else 'F' if p['type'] == 'key' else 'ArrowRight' if p['answer'] == 'ArrowLeft' else 'ArrowLeft' if p['type'] == 'key_lr' else 'wrong'
        self.event(s, now + 100, 'response', prompt_id=p['id'], response=wrong)
        self.assertEqual(s['incorrect'], 1)
        while not s['prompt']:
            now += 1000
            self.event(s, now)
        deadline = s['prompt']['deadline']
        self.event(s, deadline + 1)
        self.assertEqual(s['missed'], 1)
        self.assertEqual(s['answered'], 1)
        self.assertEqual(engine.metrics(s)['accuracy_rate'], 0)

    def test_timer_complete_and_zero_work(self):
        s = self.start(0.025)
        self.assertFalse(s['complete'])
        self.event(s, 101000)
        self.assertFalse(s['complete'])
        self.event(s, 101500)
        self.assertTrue(s['complete'])
        self.assertEqual(s['active_ms'], 1500)
        zero = self.start(0)
        self.assertTrue(zero['complete'])
        self.assertTrue(engine.metrics(zero)['meets_accuracy_threshold'])
        self.assertFalse(engine.metrics(zero)['accuracy_available'])

    def test_do_not_show_prompt_without_response_window(self):
        s = self.start(0.25)
        s['next_due'] = 110000
        for now in range(101000, 115001, 1000):
            self.event(s, now)
        self.assertTrue(s['complete'])
        self.assertEqual(s['total'], 0)

    def test_all_prompt_families_and_answers(self):
        s = engine.new_state(1, 12345)
        seen = set()
        for i in range(100):
            engine._make_prompt(s, i)
            p = s['prompt']
            seen.add(p['type'])
            self.assertNotIn('answer', engine.public_state(s, i)['prompt'])
            if p['text'].startswith('Type ') and ' + ' in p['text']:
                a, b = p['text'][5:].split(' + ')
                self.assertEqual(p['answer'], str(int(a) + int(b)))
        self.assertEqual(seen, {'key', 'key_lr', 'text'})


if __name__ == '__main__':
    unittest.main()
