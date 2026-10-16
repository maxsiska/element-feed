# element-feed

Posts a daily message, such as a lunch invitation, to an Element (Matrix) room
without running a server or holding a Matrix access token.

```text
GitHub Actions (cron) → generate_feed.py → GitHub Pages feed.xml → RSS bot in the room
```

On weekdays at 12:00 Berlin time, a workflow publishes an RSS feed that contains
one item for today. An RSS bot that is already in your room (for example the
university's Coffee Bot) picks it up and posts it. Colleagues reply with
Element's normal emoji reactions.

The script has no dependencies beyond the Python standard library.

## Setup

1. Push this repository to GitHub.
2. Under **Settings → Pages → Source**, choose **GitHub Actions**.
3. Under **Actions → Publish feed**, click **Run workflow**. While `enabled` is
   `false` in `config.json`, this publishes an empty feed at
   `https://<account>.github.io/<repository>/feed.xml`.
4. Invite Coffee Bot and subscribe it to that URL using the instructions below.
5. Set `"enabled": true` in `config.json` and push. From the next scheduled run
   on, the bot posts the message every weekday.

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
message type. Template variables and escaping rules are not described by this
help output; confirm them with the maintainer or the Mensaplan room's examples.

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

## Send a test message

Once `!coffee subscriptions` lists the feed in your test room:

1. Keep `"enabled": false` in `config.json` and push the latest project files.
2. Open **Actions → Publish feed → Run workflow** on the default branch.
3. Check **Send a labeled test message, even when recurring invitations are disabled**
   and run the workflow.
4. Wait for deployment to succeed, then for Coffee Bot to fetch the feed. The message
   begins **🧪 TEST — not a real invitation.** Try adding a ✅ reaction.

This publishes to the subscribed feed, so use it while that feed is subscribed only
in test rooms. It does not change `config.json` or enable recurring invitations.
Each new manual run has a distinct test GUID; rerunning the same workflow run reuses
its ID. Start a new **Run workflow** to send another test. Template variables still
need confirmation if you want to change the default formatting.

GitHub Pages caching and bot polling can delay delivery; it may take ten minutes
or longer. With invitations disabled, the next ordinary deployment replaces the
test entry with an empty feed. Wait for the test to arrive before deploying again.

## Configuration

| `config.json` field | Meaning |
| --- | --- |
| `enabled` | `false` publishes an empty feed (nothing gets posted) |
| `message` | Text of the post; the date is appended to the item title |
| `title`, `description` | Feed metadata |

The time and the weekdays are set by the cron line in
[.github/workflows/publish.yml](.github/workflows/publish.yml). For example,
`'30 11 * * 1-3'` posts at 11:30 Monday to Wednesday. The extra minutes
(`0,7,17`) are retries, because GitHub sometimes drops scheduled runs. Each
item's ID is the date, so the retries don't post the message twice.

**Run workflow** in the Actions tab publishes today's message when enabled,
including on weekends. With the test checkbox selected, it publishes a labeled
test instead, even when recurring invitations are disabled.

## Caveats

- GitHub's schedules can be delayed by several minutes. GitHub also disables
  them after 60 days without repository activity; re-enable them in the
  Actions tab.
- When the message actually appears also depends on how often the bot checks
  the feed.
- Holidays are not skipped.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 generate_feed.py   # writes public/feed.xml
```
