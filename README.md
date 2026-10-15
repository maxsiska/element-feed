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
4. Subscribe your room's RSS bot to that URL. Check the bot's documentation for
   the exact command.
5. Set `"enabled": true` in `config.json` and push. From the next scheduled run
   on, the bot posts the message every weekday.

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

**Run workflow** in the Actions tab publishes today's message immediately,
including on weekends.

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
