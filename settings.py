import os

SESSION_CONFIGS = [
    dict(
        name='independent_work',
        display_name='Independent work section',
        app_sequence=['independent_work'],
        num_demo_participants=1,
        default_work_minutes=35.0,
        researcher_password='admin',
    ),
]
SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.0, participation_fee=0.0, doc='',
)
PARTICIPANT_FIELDS = ['finished']
SESSION_FIELDS = []
LANGUAGE_CODE = 'en'
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = False
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin'

SECRET_KEY = os.environ.get('OTREE_SECRET_KEY', 'local-development-only-independent-work')
INSTALLED_APPS = ['otree']
