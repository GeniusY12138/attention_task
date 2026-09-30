# Independent work section

A standalone oTree experiment derived from your `attention_split_app`.
The researcher enters a participant ID and the actual required work minutes.
The participant then completes one sustained-attention work section.

There are four pages: **Researcher setup → Instructions → Task → Completion**.
There is no choice section, EMU conversion, second round, or LaterWall.

## Install and run on Mac or Ubuntu/AWS

Extract this ZIP into its own folder. Keep it separate from the existing
`save_invest_attention` project and its database.

```bash
cd attention_work_standalone
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.12 and oTree 6.0.15 were used for validation. No NumPy is required.

Set two passwords, using your own values:

```bash
export OTREE_ADMIN_PASSWORD='choose-your-admin-password'
export WORK_SETUP_PASSWORD='choose-your-researcher-setup-password'
chmod +x run.sh
./run.sh 8001
```

Open `http://localhost:8001` locally. On AWS, open `http://YOUR_SERVER_IP:8001`
after allowing that port in the instance's security group, or route an existing
reverse proxy to that port. Port 8001 lets this project run alongside an existing
experiment on port 80. Use HTTPS through your reverse proxy for remote collection.
The oTree admin username is `admin`.

`run.sh` starts the production server, disables the in-memory database option,
and defaults to this project's own on-disk `db.sqlite3`. It deliberately ignores
an inherited `DATABASE_URL` so it does not reuse the original experiment's database.
Its generated `.work_secret_key` is kept across restarts.

For an independent PostgreSQL database instead:

```bash
pip install -r requirements-production.txt
export WORK_DATABASE_URL='postgresql://USER:PASSWORD@HOST/INDEPENDENT_WORK_DATABASE'
./run.sh 8001
```

Use a new database dedicated to this project. Do not set this to the original
save-invest database. Do not run `otree resetdb` on data you want to retain.

## Assign a participant's minutes

1. In oTree admin, choose **Sessions → Create new session → Independent work section**.
2. Set the number of participants. `default_work_minutes` is an initial value only.
3. Open a participant's individual link on the session's **Links** page.
4. On **Researcher setup**, enter their ID, work minutes, and your researcher setup password.
   For returning participants, use their original participant code or study ID as the ID.
5. Click **Confirm assignment**, then hand the computer to the participant.
6. They read the instructions and click **Start work**. Only then does work time begin.

For remote participants, complete setup on your own computer, stop at the
instructions page, and send that same individual participant link to its recipient.
They will resume at the instructions and start their own timer.

Enter work minutes directly, not EMUs. Examples:

| Input | Required work time |
| --- | --- |
| 35 | 35 minutes |
| 35.4 | 35 minutes 24 seconds |
| 21.36 | 21 minutes 21.6 seconds |
| 0 | No work; the task proceeds to the completion page |

Inputs from 0 to 180 minutes are accepted. The interface accepts two decimal
places. Minutes are converted to milliseconds; there is no whole-minute rounding.
Each participant can receive a different duration within the same session.
The assignment is locked after confirmation. The setup password is cleared
before the participant proceeds and is not retained in the final export.

Use an individual participant link to resume work. The final page remains open
and has no Next button, so reopening a completed link shows the completion summary.
Keep the page sequence unchanged for sessions that are in progress.

## Leaving an SSH session

If you use `screen`, start the application inside it:

```bash
screen -S independent-work
cd /path/to/attention_work_standalone
export OTREE_ADMIN_PASSWORD='your-admin-password'
export WORK_SETUP_PASSWORD='your-researcher-setup-password'
./run.sh 8001
```

Detach with **Ctrl+A, then D**. After logging into AWS again:

```bash
screen -ls
screen -r independent-work
```

Reattach to the existing session rather than killing the process and starting a
new one every time. `screen` survives an SSH disconnection, but not an AWS reboot.
After an AWS reboot, start the application again with the same database and
passwords. For automatic startup after reboot, use a process supervisor such as
systemd. The database file must remain on persistent storage.

## Task behavior and differences from the supplied app

Preserved:

- The five original prompt families: F/J, addition, copying a two-digit number,
  left/right arrows, and numeric comparison.
- Random intervals of 10–30 seconds between prompt opportunities.
- An 8-second response deadline, matching the supplied Python code. Some older
  instructions said 5 seconds; this project's instructions consistently say 8.
- Incorrect answers, missed questions, and blur events are recorded. No extra
  work time is added for these events.
- An 80% accuracy threshold. This is reported as a result, not an automatic cash payment.

Changes for independent use and reliable resumption:

- Researcher-assigned minutes replace the earlier EMU calculations and allocation JSON files.
- Progress, prompts, responses, and scores are saved in the oTree database. The
  browser sends a heartbeat every second. A refresh resumes the saved state;
  unacknowledged time may need to be repeated (normally up to about one second).
- Hidden-tab time is not credited. A network/heartbeat gap over 2.5 seconds is
  not credited. A computer being asleep or the page being closed cannot complete
  the task. Reopening the page resumes the saved work time. An unanswered prompt
  whose deadline elapsed during an interruption is recorded as missed.
- As in the supplied app, window blur is logged but does not itself pause time
  if the task tab remains visible. Browser visibility is not proof of actual attention.
- Prompts and scoring are controlled by the server. Enter and arrow keys cannot
  accidentally submit the whole task page. Direct early form submission is rejected.
- Prompt scheduling is checked on incoming events (normally once per second),
  so actual intervals may be about one heartbeat longer than the sampled interval.
- A new prompt is not shown in the final 8 seconds, to give each scored question
  a full response window. An exceptional prompt interrupted at task completion is
  counted as censored and excluded from the accuracy denominator.
- Only the latest page instance may update a participant. Another open tab is
  paused to prevent double-counting. To resume in an older tab, reload it.

Work minutes refer to visible, connected task time, not an unconditional wall-clock
deadline. This app ends after that work requirement; it does not enforce an
additional 45-minute stay in the lab or administer the original two-session bonus.

## Export and monitoring

Use oTree's standard **Monitor** and **Data** pages. The wide export includes:

- `subject_id`, `work_minutes`, `assigned_task_seconds`, `completed_task_seconds`
- `task_finished`, `started_at_unix`, `finished_at_unix`
- `total_questions`, `scored_questions`, `correct_answers`, `incorrect_answers`,
  `answered_questions`, `missed_questions`, `censored_questions`, `blur_events`
- `accuracy_rate`, `accuracy_available`, `meets_accuracy_threshold`
- `task_log_json`, `state_json`, and the initial `rng_seed`

Accuracy is `correct_answers / scored_questions`; missed questions are included
in the denominator. If no questions were scored, `accuracy_available` is false.
A zero-minute assignment satisfies the work requirement without an accuracy score.
A positive but very short assignment with no scored questions is not classified
as meeting the accuracy threshold.

The **custom export** for `independent_work` has one row per event, including the
prompt, response, outcome, server reaction time, and browser-reported reaction time.
Server reaction time includes network delay; browser reaction time starts when
the prompt is rendered and is a client-reported measurement. State is checkpointed
on each accepted message, so an unfinished participant's saved progress is exportable.

## Validation

Validated with Python 3.12, oTree 6.0.15, and Chromium. Eight engine tests passed.
An actual browser session also checked password retries without changing minutes,
zero-minute assignments, correct/incorrect/missed responses, early-submit rejection,
refresh recovery, offline interruption, persistence after a forced server restart,
automatic completion, reopening a completed link, the production launcher, and
the custom CSV export. A 0.8-minute assignment recorded exactly 48 seconds of
credited work. No browser JavaScript errors occurred in that test.

Run the included engine checks without installing extra test libraries:

```bash
python -m unittest discover -s tests -v
```

For a quick manual end-to-end check, create a new session and assign **0.5 minutes**.
Test answers, refresh the page during work, and verify that the remaining time is
preserved and the completion summary appears. Use a new test session rather than
an actual participant's link.

The original project's private key, database, participant allocation files, and
credentials are not included in this standalone distribution.
