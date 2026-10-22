# Setup and scheduling

## 1. Connect what Claude needs

- **Claude in Chrome.** Install the extension and connect it to Claude. The
  first run asks for permission on each job site; allow linkedin.com,
  builtinnyc.com (or your Built In site), hiringcafe.com and wellfound.com.
- **Sign in** to LinkedIn and Wellfound in that Chrome.
- **Gmail.** Connect Gmail in Claude's connector settings so the report can be
  sent from your account to yourself.

## 2. Do one manual run

Ask Claude to run the skill in this repo with your config. Read the email and
adjust `title_exclude`, `max_required_years` and the profile until the ranking
looks right. Two or three runs is usually enough.

## 3. Schedule it

Ask Claude to create a scheduled task, for example *"run this every day at
8:45pm Eastern"*, with a prompt like the one below. The scheduled session
starts fresh each time, so the prompt must say where the code is and include
your config.

```text
Run my daily job board.

1. Clone https://github.com/<your-username>/daily-job-board into the working
   directory (or pull it if it's already there) and install requirements.txt.
2. Write the YAML below, exactly as given, to config.local.yaml in the repo.
3. Follow SKILL.md in the repo from start to finish, including sending the
   email. Don't ask me questions; if a board fails, send the report anyway.

<paste your config.local.yaml here>
```

The task's runs use Claude in Chrome on your computer, so set the task up to
run with your computer. If it asks for approval on every run, switch it to
automatic approval in the task's settings, if your account allows it.
Otherwise each run stops and waits.

### Picking a time

Most postings go up during US business hours. A run in the **evening Eastern
time (8-9pm)** catches a full East Coast and West Coast day. A run early in
the morning catches the same postings, just reported later.

## 4. Keep the computer awake for the run

A scheduled run needs Chrome open and the computer awake. A sleeping computer
can't run anything.

**Mac.** Schedule a wake a few minutes before the run:

```sh
sudo pmset repeat wakeorpoweron MTWRFSU 20:40:00   # every day at 8:40pm
pmset -g sched                                     # check it
sudo pmset repeat cancel                           # remove it later
```

To make the wake dependable:

- Keep the MacBook plugged in, with the lid open or an external display
  attached.
- In System Settings, under Battery (or Energy), turn on the option that
  prevents automatic sleep when plugged in and the display is off.
- Leave Chrome and the Claude desktop app running.

**Windows.** In Task Scheduler, create a task that runs a few minutes before
the job run. On its Conditions tab, check "Wake the computer to run this
task", and make sure wake timers are allowed in your power plan.

## 5. When a run fails

- **No email.** The computer was asleep, Chrome or the Claude app was closed,
  or the extension was disconnected. Check the scheduled task's run history.
- **The email says a board failed.** That site changed or blocked the request.
  The other boards still report. See `sources/README.md` to update a board
  script.
- **The same roles show up two days in a row.** A posting can be reposted or
  refreshed; boards often show those as new.
