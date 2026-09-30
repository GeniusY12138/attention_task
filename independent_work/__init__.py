from otree.api import *
import hmac
import json
import math
import os
import time
from . import engine

doc = 'Standalone sustained-attention work section with researcher-assigned minutes.'


class C(BaseConstants):
    NAME_IN_URL = 'independent_work'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1
    MAX_WORK_MINUTES = 180


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    subject_id = models.StringField(label='Participant ID')
    work_minutes = models.FloatField(min=0, max=C.MAX_WORK_MINUTES, label='Work minutes')
    setup_password = models.StringField(label='researcher_password')
    setup_complete = models.BooleanField(initial=False)
    assigned_task_seconds = models.FloatField(initial=0)
    completed_task_seconds = models.FloatField(initial=0)
    task_finished = models.BooleanField(initial=False)
    started_at_unix = models.FloatField(initial=0)
    finished_at_unix = models.FloatField(initial=0)
    rng_seed = models.IntegerField(initial=0)
    total_questions = models.IntegerField(initial=0)
    scored_questions = models.IntegerField(initial=0)
    correct_answers = models.IntegerField(initial=0)
    incorrect_answers = models.IntegerField(initial=0)
    answered_questions = models.IntegerField(initial=0)
    missed_questions = models.IntegerField(initial=0)
    censored_questions = models.IntegerField(initial=0)
    blur_events = models.IntegerField(initial=0)
    makeup_seconds = models.FloatField(initial=0)
    accuracy_rate = models.FloatField(initial=0)
    accuracy_available = models.BooleanField(initial=False)
    meets_accuracy_threshold = models.BooleanField(initial=False)
    state_json = models.LongStringField(initial='')
    task_log_json = models.LongStringField(initial='[]')


def creating_session(subsession):
    minutes = float(subsession.session.config.get('default_work_minutes', 35))
    if not math.isfinite(minutes) or not 0 <= minutes <= C.MAX_WORK_MINUTES:
        raise ValueError('default_work_minutes must be between 0 and 180.')
    for player in subsession.get_players():
        player.work_minutes = minutes
        player.participant.finished = False


def _save_state(player, state):
    player.state_json = json.dumps(state, separators=(',', ':'))
    player.task_log_json = json.dumps(state['log'], separators=(',', ':'))
    player.completed_task_seconds = state['active_ms'] / 1000
    player.task_finished = state['complete']
    player.started_at_unix = (state['started_at'] or 0) / 1000
    player.finished_at_unix = (state['finished_at'] or 0) / 1000
    for field, key in (
        ('total_questions', 'total'), ('answered_questions', 'answered'),
        ('correct_answers', 'correct'), ('incorrect_answers', 'incorrect'),
        ('missed_questions', 'missed'), ('blur_events', 'blurs'),
        ('censored_questions', 'censored'),
    ):
        setattr(player, field, state[key])
    for key, value in engine.metrics(state).items():
        setattr(player, key, value)


class ResearcherSetup(Page):
    form_model = 'player'
    form_fields = ['subject_id', 'work_minutes', 'setup_password']

    @staticmethod
    def error_message(player, values):
        expected = player.session.config.get('researcher_password', '')
        if not expected:
            return 'The researcher must WORK_SETUP_PASSWORD before starting.'
        if not hmac.compare_digest(str(values['setup_password']).encode(), expected.encode()):
            return 'Incorrect researcher password.'
        if not values['subject_id'].strip():
            return 'Enter a participant ID.'
        minutes = values['work_minutes']
        if not math.isfinite(minutes) or not 0 <= minutes <= C.MAX_WORK_MINUTES:
            return 'Enter work minutes between 0 and 180.'

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.subject_id = player.subject_id.strip()
        player.participant.label = player.subject_id
        player.setup_password = ''
        player.setup_complete = True
        player.assigned_task_seconds = round(player.work_minutes * 60, 3)
        player.rng_seed = (player.participant.id_in_session * 104729 + 77778) % 2147483647
        _save_state(player, engine.new_state(player.work_minutes, player.rng_seed))


class Instructions(Page):
    @staticmethod
    def vars_for_template(player):
        return dict(minutes_display=f'{player.work_minutes:g}')


class Task(Page):
    @staticmethod
    def vars_for_template(player):
        return dict(minutes_display=f'{player.work_minutes:g}')

    @staticmethod
    def live_method(player, data):
        recipient = data.get('client_id', '') if isinstance(data, dict) else ''
        if not player.setup_complete or not isinstance(data, dict):
            return {player.id_in_group: dict(type='error', recipient=recipient, message='Researcher setup is required.')}
        state = json.loads(player.state_json)
        now = round(time.time() * 1000)
        if not engine.advance(state, data, now):
            return {player.id_in_group: dict(type='inactive_tab', recipient=recipient)}
        _save_state(player, state)
        payload = engine.public_state(state, now)
        payload['recipient'] = recipient
        return {player.id_in_group: payload}

    @staticmethod
    def error_message(player, values):
        if not player.task_finished:
            return 'Please complete the assigned work time before continuing.'

    @staticmethod
    def before_next_page(player, timeout_happened):
        player.participant.finished = True


class End(Page):
    @staticmethod
    def vars_for_template(player):
        return dict(
            minutes_display=f'{player.completed_task_seconds / 60:g}',
            accuracy_display=f'{100 * player.accuracy_rate:.1f}%',
            zero_work=player.assigned_task_seconds == 0,
        )

    @staticmethod
    def error_message(player, values):
        return 'This work session is complete. You may close this page.'


def custom_export(players):
    yield ['session_code', 'participant_code', 'subject_id', 'event', 'server_time_ms',
           'prompt_id', 'prompt_type', 'prompt_text', 'expected_answer', 'response',
           'outcome', 'server_rt_ms', 'client_rt_ms', 'event_json']
    for player in players:
        for event in json.loads(player.task_log_json or '[]'):
            prompt = event.get('prompt') or {}
            yield [player.session.code, player.participant.code, player.subject_id,
                   event['event'], event['t'], prompt.get('id'), prompt.get('type'),
                   prompt.get('text'), prompt.get('answer'), event.get('response'),
                   event.get('outcome'), event.get('rt_ms'), event.get('client_rt_ms'),
                   json.dumps(event)]


page_sequence = [ResearcherSetup, Instructions, Task, End]
