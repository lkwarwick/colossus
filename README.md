# Colossus - Home Server

> Verson control of my personal home server.

Collosus (named after the WWII Computer, not the other one) is the name of my home server, which contains random stuff that I find useful to have running. It contains scripts and other utilities that I have setup to run on schedules.

The purpose of this repository is to keep track of the current state, incase I accidently spill water on it, or something stupider. Feel free to use any part of it yourself.

## Setup

Once you've got `git` setup on your hardware, you can clone Colossus into the home directory like so:

```bash
git clone https://github.com/lkwarwick/colossus.git .
```

Once cloned, you can run the setup script to add required logic to the `~/.bashrc`:

```bash
bash ~/scripts/setup.sh
```

---

## Scheduling Scripts

### Raspberry Pi OS Lite (headless)

To add a script to run on a schedule, edit the current user crontab:

```bash
crontab -e
```

Then add a line such as:

```bash
*/30 * * * * cd /home/pi/colossus && uv run scripts/rightmove.py >> /tmp/rightmove.log 2>&1
```

To remove all scheduled jobs:

```bash
crontab -r
```

To see what is currently set up:

```bash
crontab -l
```
