# Computer-use demo task: create a single issue

A deliberately minimal task. It tests one thing: can the agent operate the
new Create-Issue modal end-to-end through the UI? Use this when you want to
*see* the agent in the env without the cognitive load of the multi-step
escalation flow in `computer-use-task.md`.

Workflow:

1. Bring up Jirassic Park: `make run`
2. Start the agent container: `make computer-use`
3. Open <http://localhost:8081> in your browser.
4. Paste everything below the `--- PROMPT ---` line into the chat panel on the right.
5. Watch the agent operate Firefox in the panel on the left.

Verifying the result, after the agent finishes:

```bash
# the new issue should be the most-recently-created SCRUM issue
curl -fsS -H "Authorization: Bearer admin-token-jurassic" \
  "http://localhost:8080/api/search?jql=project%20%3D%20SCRUM%20ORDER%20BY%20created%20DESC&limit=1" \
  | jq '.issues[0] | {id, summary, issue_type, reporter, status}'
```

You should see an issue whose `summary` starts with `Smoke test:`.

--- PROMPT ---

You are an engineer using a Jira-like web app at http://host.docker.internal:8080.

When you first navigate to the app it will ask for an API token on the login
screen. Use this token:

<credentials>admin-token-jurassic</credentials>

Stay on this app. Do not navigate to any other domain.

## Task

Create exactly one new work item in the SCRUM project. Concretely:

1. Log in with the token above.
2. Click the blue "+ Create" button in the top navigation bar (top-right area
   of the page). A "Create Task" modal will appear in the centre of the screen.
3. In the modal, fill out the following fields. Leave everything else at its
   default value.
   - **Space** (project): `Customer App (SCRUM)` — make sure SCRUM is selected.
   - **Work type**: `Task`.
   - **Summary** (required): `Smoke test: agent-created task`
   - **Description**: `Created by a computer-use agent as a smoke test of the
     Create Issue flow. No real work to do here.`
4. Click the blue **Create** button at the bottom-right of the modal.
5. The modal should close and a toast/snackbar may briefly confirm the new
   issue's key (e.g. `SCRUM-XX created`). If you can read the key, remember it.
6. Verify the issue exists: navigate to the search page
   (<http://host.docker.internal:8080/search>), search for the summary you
   typed, and confirm the issue appears in the results.

## How to work

After every click or form submission, take a screenshot and explicitly evaluate
whether the UI changed as expected. Say "I have evaluated step N..." and only
move on once you confirm the previous step succeeded.

If a dropdown is hard to manipulate with the mouse, try the keyboard: click
the dropdown to open it, then type the first few letters to filter, and press
Enter to confirm.

If the "Summary is required" red error appears under the Summary field, that
means the field is empty — click into it and type the summary text again.

When you're done, reply with a one-paragraph summary of what you did and the
new issue's key (e.g. `SCRUM-87`).
