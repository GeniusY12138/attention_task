"""Persistent, server-scored version of the original attention task.

Only visible, connected task time is credited. Network gaps over 2.5 seconds
are not credited, and opening a page never credits the time it was closed.
All times in this module are milliseconds, from the server clock.
"""

INTERVAL_MIN_MS = 10000
INTERVAL_MAX_MS = 30000
DEADLINE_MS = 8000
MAX_HEARTBEAT_GAP_MS = 2500
ACCURACY_THRESHOLD = 0.8


def _rand(state):
    state['rng'] = state['rng'] * 48271 % 2147483647
    return state['rng'] / 2147483647


def _randint(state, low, high):
    return int(_rand(state) * (high - low + 1)) + low


def _delay(state):
    return _randint(state, INTERVAL_MIN_MS, INTERVAL_MAX_MS)


def new_state(minutes, seed):
    return dict(
        version=1, target_ms=round(minutes * 60000), active_ms=0,
        rng=seed, owner='', last_at=None, visible=False, next_due=None,
        prompt=None, prompt_number=0, started_at=None, finished_at=None,
        complete=False, total=0, answered=0, correct=0, incorrect=0,
        missed=0, blurs=0, censored=0, log=[],
    )


def _log(task, event, now, **values):
    task['log'].append(dict(event=event, t=now, **values))


def _make_prompt(state, now):
    family = _randint(state, 1, 5)
    if family == 1:
        answer = 'F' if _rand(state) < 0.5 else 'J'
        prompt = dict(type='key', answer=answer, text=f'Press {answer}',
                      hint='Use your keyboard.')
    elif family == 2:
        a, b = _randint(state, 1, 9), _randint(state, 1, 9)
        prompt = dict(type='text', answer=str(a + b), text=f'Type {a} + {b}',
                      hint='Type the number and press Enter.')
    elif family == 3:
        n = _randint(state, 10, 99)
        prompt = dict(type='text', answer=str(n), text=f'Type the number: {n}',
                      hint='Type the same two-digit number and press Enter.')
    elif family == 4:
        direction = 'Left' if _rand(state) < 0.5 else 'Right'
        prompt = dict(type='key_lr', answer='Arrow' + direction,
                      text=f'Select {direction}', hint='Press the arrow key (← or →).')
    else:
        a, b = _randint(state, 1, 9), _randint(state, 1, 9)
        answer = '>' if a > b else '<' if a < b else '='
        prompt = dict(type='text', answer=answer, text=f'Type the symbol: {a} ? {b}',
                      hint='Type >, <, or =, then press Enter.')
    state['prompt_number'] += 1
    prompt.update(id=state['prompt_number'], shown_at=now, deadline=now + DEADLINE_MS)
    state['prompt'] = prompt
    state['total'] += 1
    _log(state, 'prompt_show', now, prompt=prompt.copy())


def _close_prompt(state, outcome, now, response=None, client_rt_ms=None):
    prompt = state['prompt']
    if outcome == 'missed':
        state['missed'] += 1
    elif outcome == 'censored':
        state['censored'] += 1
    else:
        state['answered'] += 1
        state[outcome] += 1
    _log(state, 'prompt_end', now, prompt=prompt.copy(), outcome=outcome,
         response=response, rt_ms=max(0, now - prompt['shown_at']),
         client_rt_ms=client_rt_ms)
    state['prompt'] = None


def metrics(state):
    scored = state['total'] - state['censored']
    accuracy = state['correct'] / scored if scored else 0.0
    return dict(
        scored_questions=scored, accuracy_rate=accuracy,
        accuracy_available=scored > 0,
        meets_accuracy_threshold=bool(state['complete'] and (
            state['target_ms'] == 0 or (scored > 0 and accuracy >= ACCURACY_THRESHOLD)
        )),
    )


def advance(state, data, now):
    """Apply one validated browser event. Return False for an obsolete tab."""
    kind = data.get('type')
    owner = data.get('client_id')
    if kind not in ('hello', 'heartbeat', 'visibility', 'blur', 'response', 'leave'):
        return False
    if not isinstance(owner, str) or not owner or len(owner) > 100:
        return False
    if kind != 'hello' and owner != state['owner']:
        return False
    visible = data.get('visible') is True and kind != 'leave'
    if kind == 'hello':
        state['owner'] = owner
        _log(state, 'page_open', now)
        if state['started_at'] is None:
            state['started_at'] = now
            state['next_due'] = now + _delay(state)
    elif not state['complete'] and state['last_at'] is not None:
        elapsed = now - state['last_at']
        if state['visible'] and 0 <= elapsed <= MAX_HEARTBEAT_GAP_MS:
            state['active_ms'] = min(state['target_ms'], state['active_ms'] + elapsed)
        elif elapsed > MAX_HEARTBEAT_GAP_MS:
            _log(state, 'connection_gap', now, gap_ms=elapsed)
    if visible != state['visible']:
        _log(state, 'visibility', now, state='visible' if visible else 'hidden')
    state['last_at'] = now
    state['visible'] = visible
    if state['complete']:
        return True
    if kind == 'blur':
        state['blurs'] += 1
        _log(state, 'blur', now)
    if state['prompt'] and now >= state['prompt']['deadline']:
        _close_prompt(state, 'missed', now)
    if kind == 'response' and visible and state['prompt']:
        prompt = state['prompt']
        response = data.get('response')
        if data.get('prompt_id') == prompt['id'] and isinstance(response, str):
            response = response.strip()[:100]
            if prompt['type'] == 'key':
                response = response.upper()
                allowed = response in ('F', 'J')
            elif prompt['type'] == 'key_lr':
                allowed = response in ('ArrowLeft', 'ArrowRight')
            else:
                allowed = True
            if allowed:
                client_rt = data.get('client_rt_ms')
                if not isinstance(client_rt, (int, float)) or not 0 <= client_rt <= 60000:
                    client_rt = None
                outcome = 'correct' if response == prompt['answer'] else 'incorrect'
                _close_prompt(state, outcome, now, response, client_rt)
    if state['active_ms'] >= state['target_ms']:
        if state['prompt']:
            _close_prompt(state, 'censored', now)
        state['complete'] = True
        state['finished_at'] = now
        _log(state, 'task_complete', now, active_ms=state['active_ms'])
        return True
    if state['next_due'] is not None and now >= state['next_due']:
        # Retain the original independent 10–30 second prompt schedule.
        # Do not introduce a new question without time to answer it fully.
        if visible and not state['prompt'] and state['target_ms'] - state['active_ms'] >= DEADLINE_MS:
            _make_prompt(state, now)
        state['next_due'] = now + _delay(state)
    return True


def public_state(state, now):
    prompt = state['prompt']
    return dict(
        type='state', server_now=now, complete=state['complete'],
        remaining_ms=max(0, state['target_ms'] - state['active_ms']),
        visible=state['visible'],
        prompt={k: v for k, v in prompt.items() if k != 'answer'} if prompt else None,
    )
