# element-feed

Posts a daily message, such as a lunch invitation, to an Element (Matrix) room
without running a server or holding a Matrix access token.

```text
GitHub schedule ──────────┐
Hosted scheduler (API) ───┴→ GitHub Actions → GitHub Pages → Coffee Bot → Element
```

On weekdays at 11:20 Berlin time, a workflow publishes feeds that contain
one item for today, with further attempts at 11:35 and 11:50 in case GitHub delays
or drops a run. All attempts reuse the same daily entry ID. This allows time
for delivery before noon, but does not guarantee a delivery deadline. A feed bot
that is already in your room (for example the university's Coffee Bot) picks it
up and posts it. Colleagues reply with Element's normal emoji reactions.

An independent cron-job.org scheduler can also trigger the workflow at 11:25,
11:40 and 11:55 Berlin time, bypassing GitHub's scheduled-event service. It needs
the one-time setup below; committing the workflow alone does not activate it.
Each run checks the live feed first and stops if today's invitation is already
published. New invitations can only be published on weekdays from 11:15 until
12:15 Berlin time. Runs that arrive later fail visibly instead of publishing a
late lunch invitation. Disabling the feed is allowed at any time.

The script writes both `feed.xml` (RSS) and `feed.json` (JSON Feed), with the same
entry IDs, dates and content. Use JSON Feed for the custom collapsible labels
with Coffee Bot; its RSS parser strips them. No workflow changes are needed to
publish the additional file. The script has no dependencies beyond the Python
standard library.

The default invitation is **🍽️ Join the Mensa Train @ 12:30? 🚂**.
The invitation uses an HTML heading (`h3`) with no extra break before the menu
and no embedded link. Its exact size depends on the Element client.
The RSS title remains plain text with a date.
Both scheduled and manual runs include that day's live Mensa X menu,
with **Beilagen & Dessert** nested inside **Mensa X Menu**.

## Avoiding duplicate invitations

- Publication is scheduled for **11:20, 11:35 and 11:50 Europe/Berlin,
  Monday–Friday**. These attempts reuse one daily entry ID; missed or failed
  runs have another chance before noon. After hosted setup, the independent
  scheduler adds attempts at **11:25, 11:40 and 11:55**. If every attempt is
  missed or fails, there will be no new invitation that day.
- Every run uses the same `YYYY-MM-DD` entry ID and publication date for that
  Berlin day. Manual reruns, menu updates, and wording changes do not create
  another ID. The old unique test-message option has been removed.
- Keep only **one subscription** to this project in each room: `feed.json`.
  Check `!coffee subscriptions` and remove an old XML or alternate-URL
  subscription with `!coffee unsubscribe OLD_ID` in that room.
- Use local previews or a separate feed subscribed only in a test room for
  experiments. Changing the bot's template sends a sample message immediately.

The feed produces at most one distinct entry ID per date. Actual message
deduplication is performed by Coffee Bot; this project cannot enforce a strict
daily limit inside the university's bot. Its operator would need to enforce that
limit to guarantee it even after bot state loss, delivery retries, or delayed
processing of entries from different dates. Do not reset subscriptions or deploy
an old workflow with unique test IDs to force another post in the live room.

## Setup

1. Push this repository to GitHub.
2. Under **Settings → Pages → Source**, choose **GitHub Actions**.
3. Under **Actions → Publish feed**, click **Run workflow**. While `enabled` is
   `false` in `config.json`, this publishes empty feeds at
   `https://<account>.github.io/<repository>/feed.json` and `feed.xml`.
4. Invite Coffee Bot and subscribe it to that URL using the instructions below.
5. Set `"enabled": true` in `config.json` and push. From the next scheduled run
   on, the bot posts the message every weekday.

### Independent hosted scheduler (one-time setup)

GitHub's scheduled events can be delayed or dropped. A cron-job.org job calls
GitHub's `workflow_dispatch` API directly, so a missed GitHub cron event does
not prevent publication. GitHub Actions execution, Pages and Coffee Bot remain
dependencies; this is protection against the scheduler failure, not a guarantee
against every service outage.

1. Create or sign in to an account at <https://console.cron-job.org/>. In the
   account settings, enable REST API access and create an API key.
2. Create a **fine-grained** GitHub personal access token at
   <https://github.com/settings/personal-access-tokens/new>, selecting only
   `maxsiska/element-feed`, with **Actions: Read and write**. The automatically
   included Metadata permission is sufficient for the other authenticated
   requests. Choose an expiration date and record when to renew it.
3. Deploy this repository's updated workflow, then run locally:

   ```sh
   python3 setup_hosted_scheduler.py --apply
   ```

The command prompts for both keys without displaying them or saving them to
local files. The limited GitHub token is sent to cron-job.org and stored in the
job so it can trigger this repository's workflow. Do not supply your general
Git credential or paste either key into chat. Running the script without
`--apply` only shows the planned configuration, with a placeholder token.

The setup first runs a GitHub preview, then schedules a one-off external preview
approximately two minutes ahead and waits for its successful GitHub run. Neither
preview publishes a feed. Only after those checks succeed does it enable the
weekday schedule. A failed test leaves the hosted job disabled. Rerunning setup
updates the existing matching job, including when rotating an expiring token.

The hosted job sends failure, recovery and automatic-disable notifications to
the account email. These alerts cover the dispatch HTTP request. A successful
dispatch means GitHub accepted the run, not that publication or Matrix delivery
succeeded. The workflow separately verifies the public feed and reports failed
publication in Actions; enable GitHub Actions failure notifications for this
repository. Check the hosted job history if no GitHub run appears.

For a fork, update `FEED_URL` in the workflow and `REPO` in the setup script.
API references: [GitHub workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
and [cron-job.org REST API](https://docs.cron-job.org/rest-api.html).

## Coffee Bot setup

The bot's help output confirms these commands (replace the placeholders):

```text
!coffee subscribe <feed URL>
!coffee subscriptions
!coffee template <feed ID> <new template>
!coffee notice <feed ID> [true/false]
!coffee unsubscribe <feed ID>
```

Use `subscriptions`, rather than the `list` name suggested in the initial feedback.
For `notice`, the value is optional; omit the square brackets when supplying
`true` or `false`. This setting controls whether updates use Matrix's `m.notice`
message type. The command names and help text match
[maubot/rss](https://github.com/maubot/rss#templates), suggesting Coffee Bot uses
that plugin with a different command prefix. Its documented `$summary` variable
contains the RSS description; the default template only displays a title and link.
The university's exact installed version has not been confirmed.

1. Create a test room and invite the university's Coffee Bot account. Confirm its
   full Matrix account ID with the maintainer if you do not already have it.
2. Send `!coffee subscribe <feed URL>`, replacing `<feed URL>` with your public
   Pages feed URL. If the bot rejects an empty feed, test with an enabled feed
   subscribed only in the test room.
3. Send `!coffee subscriptions` to check the subscription and obtain its feed ID.
   Keep that ID for later `template`, `notice`, and `unsubscribe` commands.
4. Inspect the default formatting first; use `template` after confirming its variables.
   For live tests, use a feed subscribed only in that test room: enabling and
   publishing a feed can notify every room subscribed to it. Keep `enabled: false`
   until you are ready; an empty feed lets you check hosting without a lunch post,
   if the bot accepts empty feeds.
5. Once satisfied, invite the bot to the intended room and configure its subscription
   and template there. Confirm whether subscribing replays existing entries before
   using a feed that already contains a test invitation.

Colleagues can use Element's native emoji reactions on the resulting bot message.

### Start posting in the intended room

After testing the formatting:

1. Invite the same Coffee Bot account to the intended room and wait for it to join.
2. Send these commands as separate messages, using your public Pages URL:

   ```text
   !coffee subscribe https://<account>.github.io/<repository>/feed.json
   !coffee subscriptions
   ```

3. Use the feed ID listed in that room for these two commands, also sent separately:

   ```text
   !coffee template FEED_ID $summary
   !coffee notice FEED_ID false
   ```

   The template command sends a generic sample message. The `notice` command makes
   future invitations normal messages; each member's notification settings still
   apply. These settings must be configured in the new room even if its feed ID
   matches the test room's ID.
4. Commit and push `"enabled": true` in `config.json` to the default branch.
   No manual workflow run is needed: the next scheduled run publishes the invitation.
   The workflow targets 11:20 Europe/Berlin Monday–Friday, with further attempts
   at 11:35 and 11:50 that reuse the same daily entry ID. The earlier publication
   and additional attempts improve the chance of delivery by noon; GitHub
   execution, Pages caching, and Coffee Bot polling may still delay it.

Once the intended room subscribes, a manual run within the publication window
can publish today's invitation if it is not already in the live feed. Further
runs stop when today's entry is present and always reuse the same ID.
For later formatting experiments, use a separate test feed. If the test room no longer
needs daily posts, send `!coffee unsubscribe FEED_ID` in the **test room only**.

### Messages arrive without notifications

The matching maubot/rss plugin sends `m.notice` by default. Matrix's default
[push rules](https://spec.matrix.org/latest/client-server-api/#default-override-rules)
suppress notifications for notices, so this is a likely cause when bot posts
arrive silently. Coffee Bot's actual subscription setting still needs confirming.
To send future entries as normal `m.text` messages, send this in the subscribed
room, replacing `FEED_ID` with the ID from `!coffee subscriptions`:

```text
!coffee notice FEED_ID false
```

This changes that room's subscription for everyone; individual notification
preferences still apply. Set your room notifications to **All messages** (and
enable sound if desired), and check iOS notification permissions for Element.
Check the next day's invitation while Element is in the background. A manual
rerun of an already-seen daily entry will not generate another notification.
Existing messages will not notify retroactively. Formatting and headings do not
control notifications.

## Use JSON Feed for collapsible labels

The matching [maubot/rss plugin](https://github.com/maubot/rss/blob/master/rss/bot.py)
supports JSON Feed and uses its `content_html` for the template's `$summary`
variable. JSON Feed and the nested labels work on desktop in the test room.
The upstream [RSS sanitizer](https://github.com/kurtmckee/feedparser/blob/develop/feedparser/sanitizer.py)
strips `<summary>` but keeps `<details>`, causing generic **Details** labels.

Subscribe the room to `feed.json`, set `!coffee template FEED_ID $summary`, and
remove any existing `feed.xml` subscription from that same room. Use the ID
shown by `!coffee subscriptions`. If the bot rejects JSON Feed, confirm support
with its maintainer; do not keep both feed formats subscribed in the live room.
If an empty feed is rejected during initial setup, enable it and publish a daily
entry while it is subscribed only in the test room, then retry subscribing.

If only the invitation title/link appears, inspect the room's current template:

```text
!coffee template FEED_ID
```

The desired template is the literal `$summary`. Setting a template sends a
**generic sample message**, so do formatting experiments in a separate test room.
Changing a template does not edit messages already posted.

## Manual runs and testing

An explicitly requested **one-off 15:30 test on 19 October 2026** is implemented
in `.github/workflows/one-off-test.yml`. It is manually armed ahead of time and
waits on a GitHub runner until 15:30 Europe/Berlin, then publishes exactly
`15:30 test` through the existing feeds to subscribed rooms. It has no recurring
trigger, rejects publication outside 15:30–15:35 that day, and reuses a fixed
test entry ID on reruns. This is an exception to normal lunch publication,
authorized for this test; it does not alter the daily schedule. Bot polling
can delay the room message. This tests feed publication and delivery, not the
external scheduler's clock.

**Actions → Publish feed → Run workflow** includes a **dry_run** checkbox for
safe previews. A dry run tests the code, generates a feed and saves a short-lived
`feed-preview` artifact; it does not deploy to Pages or notify subscribed rooms.
Dry runs are allowed at any time.

An ordinary manual run uses the same configuration, daily entry ID, weekday
window and live-feed check as a scheduled run. With `enabled: false`, it clears
the feed when needed. With `enabled: true`, it can publish today's invitation
to every subscribed room during the publication window. Running it again does
not create a new ID or force Coffee Bot to resend the message.

For testing without notifications, run the unit tests or generate the files
locally; local generation does not publish anything. To test through Coffee Bot,
use a separate repository/feed subscribed **only** in a test room. Repeated
same-day runs still share an ID, so inspect local HTML for formatting changes
rather than forcing new entries into the production feed.

The message begins **🍽️ Join the Mensa Train @ 12:30? 🚂** and includes today's
live main dishes and soup inside **Mensa X Menu**, with **Beilagen & Dessert**
nested inside it. Both sections start closed on desktop, with each label shown
only once. Colleagues can react with ✅.

Element Classic on iOS displays the menu expanded because it does not support
these collapsible sections. The invitation's heading provides its own line;
explicit `<br />` breaks separate section labels and dishes, with a blank line
before the first dish in each section and an extra break before **Beilagen & Dessert**.
The browser preview cannot verify Element Classic's rendering.

The desktop layout after opening the main section is:

```text
▼ Mensa X Menu
  • Today's main dishes
  • Today's soup options
  ▶ Beilagen & Dessert
```

GitHub Pages caching and bot polling can delay delivery by ten minutes or longer.
For an already-posted daily ID, menu or formatting changes will generally not
produce another message; check the next day's entry instead.

### A scheduled invitation did not arrive

The reference `mensaplan2rss` checkout uses GitLab's `retry: 2`, allowing two
retries after a job fails. This does not recover a scheduled trigger that never
starts a job. Our three scheduled publication attempts also give a missed
trigger another chance. Each run inspects the live feed and stops if today's
entry is present; the daily ID also remains unchanged for bot deduplication.
The reference project's schedule is configured separately in GitLab and has
not been verified.

1. Open the published `feed.json` and check its item's `id`. A normal invitation
   uses today's Berlin date (`YYYY-MM-DD`). An older date or a `test-...` ID
   means the feed has not yet been replaced by today's invitation.
2. Check **Actions → Publish feed**. If today's run is absent, the scheduled
   trigger has not produced a run; check that the workflow is active and its
   schedule is on the default branch. GitHub can delay or drop scheduled runs.
   If a run failed or is pending, inspect its generation and deployment steps.
3. Each deployment checks the public feed for up to three minutes, allowing for
   Pages caching. A mismatch or unreachable feed fails the workflow. If the feed
   contains today's entry but the room has no invitation, check Coffee Bot's
   subscription URL and polling status with its maintainer. Feed verification
   does not confirm delivery in the room.

A manual run before 12:15 can recover a missed publication, but it may send an
invitation to every subscribed room. A missing feed after 12:15 produces a
`MISSED PUBLICATION` failure without a new deployment. The workflow checks the
time again immediately before deployment. It retains the daily ID and cannot
force a resend of an entry the bot has already recorded.

## Configuration

| `config.json` field | Meaning |
| --- | --- |
| `enabled` | `false` publishes an empty feed (nothing gets posted) |
| `message` | Text of the post; the date is appended to the item title |
| `title`, `description` | Feed metadata |

Use real emoji such as 🚂 in `message`; this generator does not expand emoji
shortcodes. Message text is HTML-escaped, so entering raw HTML does not add formatting.

### Live menu

`mensa.py` fetches the [official menu page](https://www.studierendenwerk-bielefeld.de/essen-trinken/speiseplan/)
once per enabled run, with a 20-second network timeout. It follows the
reference repository's selectors: the exact `menuDay` with `data-selector=YYYYMMDD`,
main dish headlines, and the labels in soup and side-dish lists. It verifies the
page's selected canteen is **Bielefeld Mensa X (13)**. The reference repository
is not needed at runtime.

The date comes from **Europe/Berlin**, including daylight saving time, rather than
the runner's local date. Only names are included: no prices, allergens, dietary
labels or climate scores. Soup joins the main dishes; small-portion variants
ending in “klein” or “(klein)” are omitted. The site's **Mensa Beilagen** list
includes desserts; these remain inside the nested **Beilagen & Dessert** section.
Repeated names and modal-dialog copies are ignored.

If today's menu is absent, the website changes, or fetching fails, the invitation
still publishes with **Today's menu is currently unavailable.** inside the menu
section, and the workflow logs a warning. It never substitutes another day's menu
or sample dishes. If dishes are available but no sides are listed, the nested
section says so. A later run keeps the same daily ID, so a bot that already posted
the invitation may not post a recovered menu. Disabled runs do not fetch the menu.

The times and the weekdays are set by the single cron entry in
[.github/workflows/publish.yml](.github/workflows/publish.yml):
`'20,35,50 11 * * 1-5'` schedules 11:20, 11:35 and 11:50 Monday–Friday.
`timezone: Europe/Berlin` handles daylight saving time. For example, change the
entry to `'30 11 * * 1-3'` for a single attempt at 11:30 Monday–Wednesday.

Ordinary manual runs also obey the weekday window. Use **dry_run** for previews
outside it. No run can bypass `enabled: false`. The dated one-off test described
above uses its own fixed ID; normal lunch runs cannot create unique test IDs.

## Caveats

- GitHub's schedules can be delayed by hours or dropped. GitHub also disables
  them after 60 days without repository activity; re-enable them in the
  Actions tab.
- When the message actually appears also depends on how often the bot checks
  the feed.
- The hosted scheduler must be configured separately, and its GitHub token
  must be renewed before expiration. Its HTTP success alone is not delivery
  confirmation.
- Holidays are not skipped.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 generate_feed.py   # writes public/feed.xml and public/feed.json
```

Tests use a small HTML fixture modeled on the official page, including its
omitted closing tags and duplicate modal content. They run without network access.
