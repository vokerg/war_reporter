# Ten-worker pilot queue

`ready-tasks.json` contains ten independent first-layer test manifests. It is example data, not the live queue.

Instantiate a real queue with:

```bash
python scripts/bootstrap_pilot.py --date YYYY-MM-DD --parent-issue ISSUE_NUMBER --region ukraine-war --output tasks/YYYY/MM/DD
```

Review and merge the planning PR before sending `копай` to worker chats.
