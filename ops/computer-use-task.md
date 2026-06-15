# Computer-use demo task: escalate SUP-1 to engineering

This is the task you paste into the chat panel of Anthropic's computer-use agent.

Workflow:

1. Bring up Jirassic Park: `make run`
2. Start the agent container: `make computer-use`
3. Open <http://localhost:8081> in your browser.
4. Paste everything below the `--- PROMPT ---` line into the chat panel on the right.
5. Watch the agent operate Firefox in the panel on the left.

The task is intentionally the same one used by the MCP demo
(`make agent-demo`) so the two recordings can be compared side-by-side:
same goal, two different interaction surfaces.

--- PROMPT ---

You are an engineer using a Jira-like web app at http://host.docker.internal:8080.

When you first navigate to the app it will ask for an API token on the login
screen. Use this token:

<credentials>admin-token-jurassic</credentials>

Stay on this app. Do not navigate to any other domain.

## Task

A customer reported issue SUP-1. Please escalate it to the platform-engineering
team (project key PLAT). Concretely:

1. Open SUP-1 (try the URL http://host.docker.internal:8080/issue?id=SUP-1, or
   navigate to it from the Issues / Search page) and read the customer's
   complaint carefully.
2. Find out who leads the PLAT project. The Projects page lists project leads,
   or you can open any PLAT issue and look at the project info on the right.
3. Create a new Bug in PLAT with:
   - A clean, engineer-facing summary based on the customer report.
   - A description that translates the customer complaint into engineering
     terms (root cause to investigate, symptoms, impact).
4. Assign the new bug to the PLAT lead.
5. Link SUP-1 to the new bug. Use link type "relates".
6. Add a comment on SUP-1 telling the customer their issue has been escalated,
   quoting the new bug's ID (e.g. "Escalated to engineering as PLAT-XX").

## How to work

After every click or form submission, take a screenshot and explicitly evaluate
whether the UI changed as expected. Say "I have evaluated step N..." and only
move on once you confirm the previous step succeeded.

If a dropdown or autocomplete is hard to manipulate with the mouse, try the
keyboard: type to filter, then Tab / Arrow / Enter to confirm.

When you're done, reply with a one-paragraph summary of what you did and the
new bug's ID.
